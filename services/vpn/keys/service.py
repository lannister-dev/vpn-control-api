from __future__ import annotations
from uuid import uuid4, UUID
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository, KeyAssignmentRepository
from services.vpn.keys.schemas import (
    VpnKeyCreate, VpnKeyInternalCreate,
    KeyAssignmentCreate,
)
from shared.database.session import AsyncDatabase
from shared.metrics import VPN_KEY_OPERATION_TOTAL
from shared.redis.client import redis_client


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

        result = await self.key_repository.create(internal.model_dump())
        VPN_KEY_OPERATION_TOTAL.labels(operation="created").inc()
        return result

    async def assign_key(self, key_id: UUID, payload: KeyAssignmentCreate) -> None:
        key = await self.key_repository.get_by_id(key_id)
        if not key:
            raise HTTPException(status_code=404, detail="Key not found",)

        if key.is_revoked:
            raise HTTPException(status_code=409, detail="Key is revoked")

        await self.assignment_repository.upsert_assignment_set_pending(
            key_id=key_id,
            node_id=payload.node_id,
            desired_state=payload.desired_state.value,
        )
        VPN_KEY_OPERATION_TOTAL.labels(operation="assigned").inc()

    async def revoke_key(self, key_id: UUID) -> None:
        key = await self.key_repository.get_by_id(key_id)
        if not key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
            )
        if key.is_revoked:
            return

        assignments = await self.assignment_repository.list_by_key_id(key_id)
        node_ids = {a.node_id for a in assignments}

        key.is_revoked = True

        await self.assignment_repository.revoke_all_for_key(key_id=key_id)
        VPN_KEY_OPERATION_TOTAL.labels(operation="revoked").inc()

        for node_id in node_ids:
            await redis_client.client.delete(f"node:{node_id}:assignments:v1")

def get_vpn_key_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> VpnKeyService:
    return VpnKeyService(session)