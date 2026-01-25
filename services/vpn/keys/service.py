from uuid import uuid4, UUID

from fastapi import HTTPException
from starlette import status

from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository, KeyAssignmentRepository
from services.vpn.keys.schemas import (
    VpnKeyCreate, VpnKeyInternalCreate,
    KeyAssignmentInternalCreate, KeyAssignmentCreate, KeyAssignmentUpdate, AssignmentDesiredState
)


class VpnService:
    @staticmethod
    async def create_key(
            payload: VpnKeyCreate,
            repository: VpnKeyRepository,
            user_repository: UserRepository
    ):
        user = await user_repository.get_by_id(payload.user_id)

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        internal = VpnKeyInternalCreate(
            **payload.model_dump(),
            client_id=str(uuid4()),
            is_revoked=False,
        )

        return await repository.create(internal.model_dump())

    @staticmethod
    async def assign_key(
            key_id: UUID,
            payload: KeyAssignmentCreate,
            key_repository: VpnKeyRepository,
            assignment_repository: KeyAssignmentRepository,
    ) -> None:
        key = await key_repository.get_by_id(key_id)
        if not key:
            raise HTTPException(status_code=404, detail="Key not found",)

        if key.is_revoked:
            raise HTTPException(status_code=409, detail="Key is revoked")

        internal_assignment = KeyAssignmentInternalCreate(
            key_id=key_id,
            node_id=payload.node_id,
            desired_state=payload.desired_state,
        )

        await assignment_repository.create(internal_assignment.model_dump())

    @staticmethod
    async def revoke_key(
            key_id: UUID,
            key_repository: VpnKeyRepository,
            assignment_repository: KeyAssignmentRepository,
    ) -> None:
        key = await key_repository.get_by_id(key_id)
        if not key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
            )
        if key.is_revoked:
            return

        key.is_revoked = True

        await assignment_repository.revoke_all_for_key(key_id=key_id)