from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from services.config import SubscriptionsExpirationConfig, get_settings
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.subscriptions.repository import SubscriptionRepository
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import VPN_KEY_OPERATION_TOTAL
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("subscription-expiration-reconciler"))


@dataclass(frozen=True)
class TickResult:
    subscriptions_expired: int
    keys_revoked: int
    placements_affected: int


class SubscriptionExpirationReconciler:
    """Deactivates expired subscriptions and revokes their VPN keys.

    Runs in tandem with `VpnKeyExpirationReconciler`: that one handles
    per-key expiration, this one handles subscription-level expiration
    (key.valid_until may outlive subscription.expires_at when subscription
    was paid for less time than key was provisioned).
    """

    def __init__(
        self,
        *,
        settings: SubscriptionsExpirationConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        cfg = settings or get_settings().subscriptions_expiration
        self._enabled = bool(cfg.enabled)
        self._interval_sec = max(30, int(cfg.tick_sec))
        self._batch_size = max(1, int(cfg.batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:subscription_expiration",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("subscription_expiration_disabled")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def run_once(self) -> TickResult | None:
        if not self._enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._execute_tick()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("subscription_expiration_tick_failed")

            watchdog.heartbeat(
                self.__class__.__name__,
                max_silence_sec=self._interval_sec * 2 + 60,
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self) -> TickResult:
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

            await session.commit()

            VPN_KEY_OPERATION_TOTAL.labels(operation="subscription_expired").inc(len(revoked_key_ids))
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
