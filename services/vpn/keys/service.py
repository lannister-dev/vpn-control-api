from __future__ import annotations
from uuid import uuid4, UUID
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.keys.schemas import (
    VpnKeyCreate, VpnKeyInternalCreate,
)
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import VPN_KEY_OPERATION_TOTAL


class VpnKeyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.key_repository = VpnKeyRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.user_repository = UserRepository(session)

    async def create_key(self, payload: VpnKeyCreate):
        user = await self.user_repository.get_by_id(payload.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        internal = VpnKeyInternalCreate(
            **payload.model_dump(),
            client_id=str(uuid4()),
            is_revoked=False,
        )

        result = await self.key_repository.create(internal.model_dump())
        VPN_KEY_OPERATION_TOTAL.labels(operation="created").inc()
        return result

    async def assign_key(self, _key_id: UUID) -> None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "Legacy key assignment API is disabled. "
                "Use /api/v1/placements for backend placement management."
            ),
        )

    async def revoke_key(self, key_id: UUID) -> None:
        key = await self.key_repository.get_by_id(key_id)
        if not key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
            )
        if key.is_revoked:
            return

        key.is_revoked = True

        await self._set_placement_inactive(key_id=key_id)
        VPN_KEY_OPERATION_TOTAL.labels(operation="revoked").inc()

    async def _set_placement_inactive(self, *, key_id: UUID) -> None:
        placement = await self.placement_repository.get_by_key_id(key_id)
        if placement is None:
            return

        await self.placement_repository.upsert_set_pending(
            key_id=key_id,
            backend_node_id=placement.backend_node_id,
            desired_state=PlacementDesiredState.inactive.value,
            sticky_until=placement.sticky_until,
            last_migration_reason="key_revoke",
        )


def get_vpn_key_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> VpnKeyService:
    return VpnKeyService(session)
