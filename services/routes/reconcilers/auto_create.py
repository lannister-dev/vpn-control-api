from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import select

from services.config import get_settings
from services.entry.models import EntryBackendAssignment
from services.nodes.models import VpnNode
from services.routes.models import Route
from services.routes.repository import RouteRepository, TransportProfileRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger


class RouteAutoCreateReconciler(Reconciler):
    """Creates a missing Route(entry, backend, reality) for every active+enabled
    entry_backend_assignment, and deactivates reality routes whose assignment was
    removed. Does not reactivate routes deactivated in the admin panel — admin
    deactivation is authoritative.
    """

    name = "route_auto_create"

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        interval_sec = max(30, get_settings().routes.warmup_tick_sec)
        super().__init__(
            interval_sec=interval_sec,
            tick_lock=tick_lock,
            lock_ttl_sec=max(30, interval_sec * 2),
        )
        self._session_maker = AsyncDatabase.get_session_maker()
        self._log = StructuredLogger(logging.getLogger("route-auto-create-reconciler"))

    async def tick(self) -> dict:
        async with self._session_maker() as session:
            reality = await TransportProfileRepository(session).list_active(limit=10)
            reality_profile = next(
                (p for p in reality if p.security == "reality" and p.network == "tcp"),
                None,
            )
            if reality_profile is None:
                return {"reason": "no_reality_profile"}

            assignments_stmt = select(
                EntryBackendAssignment, VpnNode,
            ).join(
                VpnNode, VpnNode.id == EntryBackendAssignment.entry_node_id,
            ).where(
                EntryBackendAssignment.is_active.is_(True),
                EntryBackendAssignment.enabled.is_(True),
            )
            rows = (await session.execute(assignments_stmt)).all()

            want: set[tuple[UUID, UUID]] = set()
            for ea, entry in rows:
                want.add((entry.id, ea.backend_node_id))

            created = 0
            reactivated = 0
            announce: list[tuple[UUID, UUID]] = []
            for entry_id, backend_id in want:
                route = await RouteRepository(session).get_by_triple(
                    backend_node_id=backend_id,
                    entry_node_id=entry_id,
                    transport_profile_id=reality_profile.id,
                )
                if route is None:
                    backend = await session.get(VpnNode, backend_id)
                    entry = await session.get(VpnNode, entry_id)
                    name = f"{entry.name}→{backend.name}·reality"
                    session.add(Route(
                        id=uuid4(),
                        name=name,
                        node_id=backend_id,
                        entry_node_id=entry_id,
                        transport_profile_id=reality_profile.id,
                        health_status="healthy",
                        base_weight=50,
                        effective_weight=50,
                        is_active=True,
                    ))
                    created += 1
                    announce.append((entry_id, backend_id))

            existing_stmt = select(Route).where(
                Route.is_active.is_(True),
                Route.entry_node_id.is_not(None),
                Route.transport_profile_id == reality_profile.id,
            )
            existing = (await session.execute(existing_stmt)).scalars().all()
            deactivated = 0
            for r in existing:
                if (r.entry_node_id, r.node_id) not in want:
                    r.is_active = False
                    deactivated += 1

            if created or reactivated or deactivated:
                from services.routes.service import RouteService
                route_service = RouteService(session)
                for entry_id, backend_id in announce:
                    await route_service.sync_entry_upstream(
                        entry_node_id=entry_id,
                        backend_node_id=backend_id,
                    )
                await session.commit()
                self._log.info(
                    "route_auto_create_tick",
                    created=created,
                    reactivated=reactivated,
                    deactivated=deactivated,
                    announced=len(announce),
                    total_want=len(want),
                )
            return {"created": created, "reactivated": reactivated, "deactivated": deactivated}
