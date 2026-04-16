import logging
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.entry.constants import RELAY_POOL_TTL_SEC, ROLE_BACKEND, ROLE_ENTRY
from services.entry.models import EntryBackendAssignment
from services.entry.repository import EntryBackendAssignmentRepository
from services.entry.schemas import (
    EntryBackendAssignIn,
    EntryBackendUpdateIn,
    RelayBackendOut,
    RelayPoolOut,
)
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

logger_entry = StructuredLogger(logging.getLogger("entry-service"))


class EntryNotFoundError(LookupError):
    pass


class BackendNotFoundError(LookupError):
    pass


class EntryRoleError(ValueError):
    pass


class EntryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.assignment_repo = EntryBackendAssignmentRepository(session)
        self.node_repo = VpnNodeRepository(session)
        self.reality_port = int(get_settings().probe.target_port)

    # ------------------------------------------------------------------
    # Public (relay-facing)
    # ------------------------------------------------------------------

    async def get_relay_pool(self, entry_node_id: UUID) -> RelayPoolOut:
        entry = await self.node_repo.get_by_id(entry_node_id)
        if entry is None or not entry.is_active:
            raise EntryNotFoundError(f"entry node {entry_node_id} not found")
        if entry.role != ROLE_ENTRY:
            raise EntryRoleError(
                f"node {entry_node_id} has role '{entry.role}', expected '{ROLE_ENTRY}'"
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
                )
            )

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
            return await self.assignment_repo.update_by_id(
                existing.id,
                {
                    "weight": payload.weight,
                    "enabled": payload.enabled,
                    "is_active": True,
                },
            )

        return await self.assignment_repo.create(
            {
                "entry_node_id": entry_node_id,
                "backend_node_id": payload.backend_node_id,
                "weight": payload.weight,
                "enabled": payload.enabled,
            }
        )

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
        data = payload.model_dump(exclude_unset=True)
        if not data:
            return existing
        return await self.assignment_repo.update_by_id(existing.id, data)

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
        await self.assignment_repo.update_by_id(existing.id, {"is_active": False})
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _require_entry(self, entry_node_id: UUID) -> VpnNode:
        entry = await self.node_repo.get_by_id(entry_node_id)
        if entry is None or not entry.is_active:
            raise EntryNotFoundError(f"entry node {entry_node_id} not found")
        if entry.role != ROLE_ENTRY:
            raise EntryRoleError(
                f"node {entry_node_id} has role '{entry.role}', expected '{ROLE_ENTRY}'"
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


async def get_entry_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> EntryService:
    return EntryService(session)
