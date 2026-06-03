from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.config import VpnKeyConfig, get_settings
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.subscriptions.cache import SubscriptionCacheInvalidator
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import VPN_KEY_OPERATION_TOTAL
from shared.reconciler.base import Reconciler
from shared.redis.client import redis_client
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("vpn-key-expiration-reconciler"))


class VpnKeyExpirationReconciler(Reconciler):
    name = "vpn_key_expiration"

    def __init__(
        self,
        *,
        vpn_key_settings: VpnKeyConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = vpn_key_settings or get_settings().vpn_key
        super().__init__(
            interval_sec=max(30, int(settings.expiration_tick_sec)),
            enabled=bool(settings.expiration_enabled),
            tick_lock=tick_lock,
        )
        self._batch_size = max(1, int(settings.expiration_batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
        async with self._session_maker() as session:
            key_repo = VpnKeyRepository(session)
            placement_repo = UserPlacementRepository(session)
            transport = NodeAgentPlacementTransport(session)

            revoked_key_ids = await key_repo.bulk_revoke_expired(limit=self._batch_size)
            if not revoked_key_ids:
                return 0

            now = datetime.now(timezone.utc)
            affected_placement_ids = await placement_repo.bulk_set_desired_state_for_keys(
                key_ids=revoked_key_ids,
                desired_state=PlacementDesiredState.inactive.value,
                last_migration_reason="key_expired",
                updated_at=now,
            )

            if affected_placement_ids:
                await transport.enqueue_for_placement_ids(affected_placement_ids)

            cache_invalidator = SubscriptionCacheInvalidator(session, redis_client)
            await cache_invalidator.invalidate_by_key_ids(revoked_key_ids)

            await session.commit()

            count = len(revoked_key_ids)
            VPN_KEY_OPERATION_TOTAL.labels(operation="expired").inc(count)
            logger.info(
                "vpn_keys_expired",
                revoked=count,
                placements_affected=len(affected_placement_ids),
            )
            return count
