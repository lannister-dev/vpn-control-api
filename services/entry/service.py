import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.entry.constants import ENTRY_ROLES, RELAY_POOL_TTL_SEC, ROLE_BACKEND, POOL_CHANGED_EVENT_TYPE
from services.entry.exceptions import EntryNotFoundError, EntryRoleError, BackendNotFoundError
from services.entry.models import EntryBackendAssignment
from services.entry.repository import EntryBackendAssignmentRepository
from services.entry.schemas import (
    EntryBackendAssignIn,
    EntryBackendAssignmentCreate,
    EntryBackendAssignmentUpdate,
    EntryBackendUpdateIn,
    EntryPoolChangedPayload,
    RelayBackendOut,
    RelayPoolOut,
)
from services.nodes.agent.repository import NodeTransportOutboxRepository
from services.nodes.agent.schemas import AgentSubjects, OutboxEnqueueItem
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

logger_entry = StructuredLogger(logging.getLogger("entry-service"))


class EntryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.assignment_repo = EntryBackendAssignmentRepository(session)
        self.node_repo = VpnNodeRepository(session)
        self.outbox_repo = NodeTransportOutboxRepository(session)
        settings = get_settings()
        self.reality_port = int(settings.probe.target_port)
        self._subjects = AgentSubjects(
            command_prefix=settings.nats.js_command_subject_prefix,
            result_prefix=settings.nats.js_result_subject_prefix,
            snapshot_prefix=settings.nats.js_snapshot_subject_prefix,
            heartbeat_prefix=settings.nats.js_heartbeat_subject_prefix,
            sync_report_prefix=settings.nats.js_sync_report_subject_prefix,
        )

    # ------------------------------------------------------------------
    # Public (relay-facing)
    # ------------------------------------------------------------------

    async def \
            get_relay_pool(self, entry_node_id: UUID) -> RelayPoolOut:
        entry = await self.node_repo.get_by_id(entry_node_id)
        if entry is None or not entry.is_active:
            raise EntryNotFoundError(f"entry node {entry_node_id} not found")
        if entry.role not in ENTRY_ROLES:
            raise EntryRoleError(
                f"node {entry_node_id} has role '{entry.role}', expected one of {sorted(ENTRY_ROLES)}"
            )

        assignments = await self.assignment_repo.list_by_entry(entry_node_id)
        backend_ids = [a.backend_node_id for a in assignments]
        backends = await self.node_repo.list_by_ids(backend_ids)
        backends_by_id: dict[UUID, VpnNode] = {b.id: b for b in backends}

        items: list[RelayBackendOut] = []
        for a in assignments:
            backend = backends_by_id.get(a.backend_node_id)
            if backend is None or not backend.is_active:
                continue
            address = self._resolve_backend_address(backend)
            if address is None:
                continue
            admin_ok = (
                    a.enabled
                    and backend.is_enabled
                    and not backend.is_draining
            )
            items.append(
                RelayBackendOut(
                    id=backend.id,
                    address=address,
                    port=self.reality_port,
                    weight=a.weight,
                    enabled=admin_ok,
                    rank=a.rank,
                )
            )

        # Keep output deterministic so data-plane diffs stay minimal
        # when nothing else changed. Primary tier first.
        items.sort(key=lambda b: (b.rank, str(b.id)))

        return RelayPoolOut(
            entry_id=entry_node_id,
            generation=self._generation(assignments),
            ttl_seconds=RELAY_POOL_TTL_SEC,
            backends=items,
        )

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    async def list_assignments(self, entry_node_id: UUID) -> list[EntryBackendAssignment]:
        await self._require_entry(entry_node_id)
        return await self.assignment_repo.list_by_entry(entry_node_id)

    async def assign_backend(
            self,
            entry_node_id: UUID,
            payload: EntryBackendAssignIn,
    ) -> EntryBackendAssignment:
        await self._require_entry(entry_node_id)
        await self._require_backend(payload.backend_node_id)

        existing = await self.assignment_repo.get_by_entry_and_backend(
            entry_node_id=entry_node_id,
            backend_node_id=payload.backend_node_id,
        )
        if existing is not None:
            update = EntryBackendAssignmentUpdate(
                weight=payload.weight,
                enabled=payload.enabled,
                rank=payload.rank,
                is_active=True,
            )
            result = await self.assignment_repo.update_by_id(
                existing.id, update.model_dump(),
            )
        else:
            create = EntryBackendAssignmentCreate(
                entry_node_id=entry_node_id,
                backend_node_id=payload.backend_node_id,
                weight=payload.weight,
                enabled=payload.enabled,
                rank=payload.rank,
            )
            result = await self.assignment_repo.create(create.model_dump())

        await self._enqueue_pool_snapshot(entry_node_id)
        return result

    async def update_assignment(
            self,
            entry_node_id: UUID,
            backend_node_id: UUID,
            payload: EntryBackendUpdateIn,
    ) -> EntryBackendAssignment | None:
        existing = await self.assignment_repo.get_by_entry_and_backend(
            entry_node_id=entry_node_id,
            backend_node_id=backend_node_id,
        )
        if existing is None or not existing.is_active:
            return None
        update = EntryBackendAssignmentUpdate(**payload.model_dump(exclude_unset=True))
        data = update.model_dump(exclude_unset=True)
        if not data:
            return existing
        result = await self.assignment_repo.update_by_id(existing.id, data)
        await self._enqueue_pool_snapshot(entry_node_id)
        return result

    async def remove_assignment(
            self,
            entry_node_id: UUID,
            backend_node_id: UUID,
    ) -> bool:
        existing = await self.assignment_repo.get_by_entry_and_backend(
            entry_node_id=entry_node_id,
            backend_node_id=backend_node_id,
        )
        if existing is None or not existing.is_active:
            return False
        deactivate = EntryBackendAssignmentUpdate(is_active=False)
        await self.assignment_repo.update_by_id(existing.id, deactivate.model_dump(exclude_unset=True))
        await self._enqueue_pool_snapshot(entry_node_id)
        return True

    # ------------------------------------------------------------------
    # Fan-out: backend health → every entry that includes it
    # ------------------------------------------------------------------

    async def notify_backend_health_changed(self, backend_node_id: UUID) -> int:
        entry_ids = await self.assignment_repo.list_entry_ids_for_backend(backend_node_id)
        for entry_id in entry_ids:
            await self._enqueue_pool_snapshot(entry_id)
        return len(entry_ids)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _require_entry(self, entry_node_id: UUID) -> VpnNode:
        entry = await self.node_repo.get_by_id(entry_node_id)
        if entry is None or not entry.is_active:
            raise EntryNotFoundError(f"entry node {entry_node_id} not found")
        if entry.role not in ENTRY_ROLES:
            raise EntryRoleError(
                f"node {entry_node_id} has role '{entry.role}', expected one of {sorted(ENTRY_ROLES)}"
            )
        return entry

    async def _require_backend(self, backend_node_id: UUID) -> VpnNode:
        backend = await self.node_repo.get_by_id(backend_node_id)
        if backend is None or not backend.is_active:
            raise BackendNotFoundError(f"backend node {backend_node_id} not found")
        if backend.role != ROLE_BACKEND:
            raise EntryRoleError(
                f"node {backend_node_id} has role '{backend.role}', expected '{ROLE_BACKEND}'"
            )
        return backend

    @staticmethod
    def _resolve_backend_address(backend: VpnNode) -> str | None:
        candidate = (backend.reality_ip or backend.internal_wg_ip or "").strip()
        return candidate or None

    @staticmethod
    def _generation(assignments: list[EntryBackendAssignment]) -> int:
        if not assignments:
            return 0
        latest = max(a.updated_at for a in assignments)
        return int(latest.timestamp())

    async def _enqueue_pool_snapshot(self, entry_node_id: UUID) -> None:
        pool = await self.get_relay_pool(entry_node_id)
        event_id = str(uuid4())
        emitted_at = datetime.now(timezone.utc)
        payload = EntryPoolChangedPayload(
            event_id=event_id,
            node_id=str(entry_node_id),
            emitted_at=emitted_at,
            pool=pool,
        )
        item = OutboxEnqueueItem(
            node_id=entry_node_id,
            event_type=POOL_CHANGED_EVENT_TYPE,
            aggregate_id=None,
            subject=self._subjects.pool_changed(str(entry_node_id)),
            payload=payload.model_dump(mode="json"),
            message_id=f"pool-changed:{entry_node_id}:{pool.generation}:{event_id}",
        )
        await self.outbox_repo.enqueue_many([item])


async def get_entry_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> EntryService:
    return EntryService(session)
