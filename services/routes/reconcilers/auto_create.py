from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

from sqlalchemy import select

from services.config import get_settings
from services.entry.models import EntryBackendAssignment
from services.nodes.models import VpnNode
from services.routes.models import Route
from services.routes.repository import RouteRepository, TransportProfileRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger


class RouteAutoCreateReconciler:
    """Ensures every active+enabled entry_backend_assignment has a matching
    Route(entry, backend, transport_profile) — Reality only for now. Reactivates
    routes whose assignment came back; deactivates routes whose assignment was
    removed. Removes the need to hand-INSERT routes on every node rotation.
    """

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._interval_sec = max(30, get_settings().routes.warmup_tick_sec)
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:route_auto_create",
            ttl_sec=max(30, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._log = StructuredLogger(logging.getLogger("route-auto-create-reconciler"))

    async def start(self) -> None:
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

    async def run_once(self):
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
                self._log.exception("route_auto_create_tick_failed")
            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self) -> dict:
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
                elif not route.is_active:
                    route.is_active = True
                    route.health_status = "healthy"
                    reactivated += 1
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
