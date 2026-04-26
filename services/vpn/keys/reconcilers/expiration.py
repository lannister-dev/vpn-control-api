from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from services.config import VpnKeyConfig, get_settings
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.vpn.keys.repository import VpnKeyRepository
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import VPN_KEY_OPERATION_TOTAL
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("vpn-key-expiration-reconciler"))


class VpnKeyExpirationReconciler:
    def __init__(
        self,
        *,
        vpn_key_settings: VpnKeyConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = vpn_key_settings or get_settings().vpn_key
        self._enabled = bool(settings.expiration_enabled)
        self._interval_sec = max(30, int(settings.expiration_tick_sec))
        self._batch_size = max(1, int(settings.expiration_batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:vpn_key_expiration",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("vpn_key_expiration_disabled")
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

    async def run_once(self) -> int | None:
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
                logger.exception("vpn_key_expiration_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        async with self._session_maker() as session:
            key_repo = VpnKeyRepository(session)
            placement_repo = UserPlacementRepository(session)
            transport = NodeAgentPlacementTransport(session)

            # 1) Bulk: SELECT expired key IDs + UPDATE is_revoked=true
            revoked_key_ids = await key_repo.bulk_revoke_expired(limit=self._batch_size)
            if not revoked_key_ids:
                return 0

            # 2) Bulk: UPDATE all placements for those keys → inactive/pending
            now = datetime.now(timezone.utc)
            affected_placement_ids = await placement_repo.bulk_set_desired_state_for_keys(
                key_ids=revoked_key_ids,
                desired_state=PlacementDesiredState.inactive.value,
                last_migration_reason="key_expired",
                updated_at=now,
            )

            # 3) Bulk: INSERT outbox entries for affected placements
            if affected_placement_ids:
                await transport.enqueue_for_placement_ids(affected_placement_ids)

            await session.commit()

            count = len(revoked_key_ids)
            VPN_KEY_OPERATION_TOTAL.labels(operation="expired").inc(count)
            logger.info(
                "vpn_keys_expired",
                revoked=count,
                placements_affected=len(affected_placement_ids),
            )
            return count
