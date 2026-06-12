from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.nodes.agent.models import NodeTransportState
from services.nodes.constants import ROLE_BACKEND, ROLE_ENTRY, ROLE_WHITELIST_ENTRY
from services.nodes.models import VpnNode
from services.placements.repository import UserPlacementRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("snapshot-freshness-reconciler"))

TICK_SEC = 60
SETTLE_SEC = 30


class NodeSnapshotFreshnessReconciler(Reconciler):
    """Safety net: snapshot any serving node whose desired routing changed after
    its last snapshot.

    Incremental placement-command delivery can be missed (e.g. the load balancer
    rewrites a key's backend override but the outbox push never lands), leaving
    the agent on stale routing with no recovery short of a manual snapshot. This
    reconciler detects the drift from the DB alone and triggers the snapshot.

    Drift signal: max(vpn_key.updated_at, user_placement.created_at) for the
    node's rows. Both move only on a DESIRED change (override edit / new
    placement) and NOT when the agent applies a command (that bumps
    user_placement.updated_at/applied_version), so comparing against the snapshot
    time cannot loop.
    """

    name = "node_snapshot_freshness"

    def __init__(
        self,
        *,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        snapshot_trigger: Callable[..., Awaitable[None]] | None = None,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        super().__init__(interval_sec=TICK_SEC, tick_lock=tick_lock)
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._snapshot_trigger = snapshot_trigger

    async def tick(self) -> int:
        if self._snapshot_trigger is None:
            return 0
        stale: list[UUID] = []
        async with self._session_maker() as session:
            nodes = await self._serving_nodes(session)
            placement_repo = UserPlacementRepository(session)
            now = datetime.now(timezone.utc)
            settle = timedelta(seconds=SETTLE_SEC)
            for node in nodes:
                if node.role in (ROLE_ENTRY, ROLE_WHITELIST_ENTRY):
                    rows = await placement_repo.list_transport_rows_for_entry(entry_node_id=node.id)
                else:
                    rows = await placement_repo.list_transport_rows_for_backend(backend_node_id=node.id)
                if not rows:
                    continue
                latest = max(max(key.updated_at, placement.created_at) for placement, key in rows)
                if now - latest < settle:
                    continue
                last_snapshot = await self._last_snapshot_at(session, node.id)
                if last_snapshot is None or latest > last_snapshot:
                    stale.append(node.id)

        for node_id in stale:
            try:
                await self._snapshot_trigger(node_id=node_id, reason="freshness_drift")
            except Exception:
                logger.exception("snapshot_freshness_trigger_failed", node_id=str(node_id))
        if stale:
            logger.info("snapshot_freshness_triggered", nodes=len(stale))
        return len(stale)

    @staticmethod
    async def _serving_nodes(session: AsyncSession) -> list[VpnNode]:
        result = await session.scalars(
            select(VpnNode).where(
                VpnNode.role.in_((ROLE_ENTRY, ROLE_WHITELIST_ENTRY, ROLE_BACKEND)),
                VpnNode.is_active.is_(True),
                VpnNode.is_enabled.is_(True),
                VpnNode.is_draining.is_(False),
            )
        )
        return list(result.all())

    @staticmethod
    async def _last_snapshot_at(session: AsyncSession, node_id: UUID) -> datetime | None:
        return await session.scalar(
            select(NodeTransportState.last_snapshot_generated_at).where(
                NodeTransportState.node_id == node_id
            )
        )
