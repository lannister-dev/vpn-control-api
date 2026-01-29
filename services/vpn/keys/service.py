from __future__ import annotations
from uuid import uuid4, UUID
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository, KeyAssignmentRepository
from services.vpn.keys.schemas import (
    VpnKeyCreate, VpnKeyInternalCreate,
    KeyAssignmentInternalCreate, KeyAssignmentCreate
)
from shared.database.session import AsyncDatabase


class VpnKeyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.key_repository = VpnKeyRepository(session)
        self.user_repository = UserRepository(session)
        self.assignment_repository = KeyAssignmentRepository(session)

    async def create_key(self, payload: VpnKeyCreate):
        user = await self.user_repository.get_by_id(payload.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        internal = VpnKeyInternalCreate(
            **payload.model_dump(),
            client_id=str(uuid4()),
            is_revoked=False,
        )

        return await self.key_repository.create(internal.model_dump())

    async def assign_key(self, key_id: UUID, payload: KeyAssignmentCreate) -> None:
        key = await self.key_repository.get_by_id(key_id)
        if not key:
            raise HTTPException(status_code=404, detail="Key not found",)

        if key.is_revoked:
            raise HTTPException(status_code=409, detail="Key is revoked")

        internal_assignment = KeyAssignmentInternalCreate(
            key_id=key_id,
            node_id=payload.node_id,
            desired_state=payload.desired_state,
        )

        await  self.assignment_repository.create(
            internal_assignment.model_dump()
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

        await self.assignment_repository.revoke_all_for_key(key_id=key_id)

def get_vpn_key_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> VpnKeyService:
    return VpnKeyService(session)