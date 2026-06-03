from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.config import TrafficConfig, get_settings
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.traffic.users.constants import _RESET_REASON
from services.traffic.users.reset_policy import RESETTABLE_STRATEGIES, reset_cutoff
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.subscriptions.repository import SubscriptionRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("traffic-reset-reconciler"))


class TrafficResetReconciler(Reconciler):
    name = "traffic_reset"

    def __init__(
        self,
        *,
        traffic_settings: TrafficConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = traffic_settings or get_settings().traffic
        interval_sec = max(60, int(settings.reset_tick_sec))
        super().__init__(
            interval_sec=interval_sec,
            enabled=bool(settings.reset_enabled),
            tick_lock=tick_lock,
            lock_ttl_sec=max(120, interval_sec * 2),
        )
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> None:
        now = datetime.now(timezone.utc)
        total_reset = 0

        for strategy in RESETTABLE_STRATEGIES:
            cutoff = reset_cutoff(strategy, now)
            async with self._session_maker() as session:
                sub_repo = SubscriptionRepository(session)
                key_repo = VpnKeyRepository(session)
                placement_repo = UserPlacementRepository(session)
                transport = NodeAgentPlacementTransport(session)

                subs = await sub_repo.list_needing_traffic_reset(
                    strategy=strategy.value, reset_before=cutoff,
                )
                if not subs:
                    continue

                for sub in subs:
                    unrevoked_key_ids = await key_repo.bulk_reset_traffic_by_subscription(sub.id)
                    sub.used_traffic_bytes = 0
                    sub.last_traffic_reset_at = now
                    sub.traffic_warning_threshold_pct = 0
                    sub.updated_at = now

                    for key_id in unrevoked_key_ids:
                        await placement_repo.set_desired_state_for_key(
                            key_id=key_id,
                            desired_state=PlacementDesiredState.active.value,
                            last_migration_reason=_RESET_REASON,
                            updated_at=now,
                        )
                        await transport.enqueue_for_key_state(
                            key_id=key_id,
                            desired_state=PlacementDesiredState.active.value,
                        )

                    total_reset += 1

                await session.commit()

        if total_reset > 0:
            logger.info("traffic_reset_tick", subscriptions_reset=total_reset)
