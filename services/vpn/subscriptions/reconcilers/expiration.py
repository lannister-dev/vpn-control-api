from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from services.config import SubscriptionsExpirationConfig, get_settings
from services.notifications.service import NotificationService
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.subscriptions.cache import SubscriptionCacheInvalidator
from services.vpn.subscriptions.repository import (
    SubscriptionDeviceRepository,
    SubscriptionRepository,
)
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import (
    EXPIRED_SUBSCRIPTIONS_TOTAL,
    VPN_KEY_OPERATION_TOTAL,
)
from shared.reconciler.base import Reconciler
from shared.redis.client import redis_client
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("subscription-expiration-reconciler"))


@dataclass(frozen=True)
class TickResult:
    subscriptions_expired: int
    keys_revoked: int
    placements_affected: int


class SubscriptionExpirationReconciler(Reconciler):
    name = "subscription_expiration"

    def __init__(
        self,
        *,
        settings: SubscriptionsExpirationConfig | None = None,
        tick_lock: RedisTickLock | None = None,
        notifications: NotificationService | None = None,
    ):
        cfg = settings or get_settings().subscriptions_expiration
        super().__init__(
            interval_sec=max(30, int(cfg.tick_sec)),
            enabled=bool(cfg.enabled),
            tick_lock=tick_lock,
        )
        self._batch_size = max(1, int(cfg.batch_size))
        self._notifications = notifications
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> TickResult:
        async with self._session_maker() as session:
            sub_repo = SubscriptionRepository(session)
            key_repo = VpnKeyRepository(session)
            placement_repo = UserPlacementRepository(session)
            transport = NodeAgentPlacementTransport(session)

            now = datetime.now(timezone.utc)
            expired = await sub_repo.list_expired_active(now=now, limit=self._batch_size)
            if not expired:
                return TickResult(0, 0, 0)

            sub_ids = [s.id for s in expired]
            revoked_key_ids = await key_repo.bulk_revoke_by_subscription_ids(
                subscription_ids=sub_ids,
            )

            affected_placement_ids: list = []
            if revoked_key_ids:
                affected_placement_ids = await placement_repo.bulk_set_desired_state_for_keys(
                    key_ids=revoked_key_ids,
                    desired_state=PlacementDesiredState.inactive.value,
                    last_migration_reason="subscription_expired",
                    updated_at=now,
                )
                if affected_placement_ids:
                    await transport.enqueue_for_placement_ids(affected_placement_ids)

            await sub_repo.bulk_deactivate(sub_ids)
            await SubscriptionDeviceRepository(session).bulk_deactivate_by_subscription_ids(sub_ids)

            cache_invalidator = SubscriptionCacheInvalidator(session, redis_client)
            await cache_invalidator.invalidate_by_subscription_ids(sub_ids)

            await session.commit()

            await self._emit_expired_events(session, expired)

            VPN_KEY_OPERATION_TOTAL.labels(operation="subscription_expired").inc(len(revoked_key_ids))
            EXPIRED_SUBSCRIPTIONS_TOTAL.inc(len(sub_ids))
            logger.info(
                "subscriptions_expired",
                subscriptions=len(sub_ids),
                keys_revoked=len(revoked_key_ids),
                placements_affected=len(affected_placement_ids),
            )
            return TickResult(
                subscriptions_expired=len(sub_ids),
                keys_revoked=len(revoked_key_ids),
                placements_affected=len(affected_placement_ids),
            )

    async def _emit_expired_events(self, session, expired) -> None:
        if self._notifications is None:
            return
        paid: list = []
        trial: list = []
        for s in expired:
            plan = getattr(s, "plan", None)
            if plan is None:
                continue
            (paid if plan.price_rub > 0 else trial).append(s)
        relevant = paid + trial
        if not relevant:
            return
        users = await UserRepository(session).list_by_ids([s.user_id for s in relevant])
        by_id = {u.id: u for u in users}
        for s in paid:
            user = by_id.get(s.user_id)
            if user is None or not user.telegram_id:
                continue
            try:
                await self._notifications.publish_subscription_expired(
                    telegram_id=int(user.telegram_id),
                    username=getattr(user, "username", None),
                    plan_name=getattr(s.plan, "name", None),
                )
            except Exception:
                logger.exception("subscription_expired_publish_failed", subscription_id=str(s.id))
        for s in trial:
            user = by_id.get(s.user_id)
            if user is None or not user.telegram_id:
                continue
            try:
                await self._notifications.publish_trial_expired(
                    telegram_id=int(user.telegram_id),
                    username=getattr(user, "username", None),
                    plan_name=getattr(s.plan, "name", None),
                )
            except Exception:
                logger.exception("trial_expired_publish_failed", subscription_id=str(s.id))
