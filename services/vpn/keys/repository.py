from __future__ import annotations

from typing import Sequence
from uuid import UUID

from fastapi import Depends
from sqlalchemy import update, select
from sqlalchemy import and_, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.vpn.keys.models import KeyAssignment, VpnKey
from services.vpn.keys.schemas import AssignmentDesiredState, AssignmentAppliedState
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class VpnKeyRepository(BaseRepository[VpnKey]):
    def __init__(self, session: AsyncSession):
        super().__init__(VpnKey, session)


async def get_vpn_key_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> VpnKeyRepository:
    return VpnKeyRepository(session)


class KeyAssignmentRepository(BaseRepository[KeyAssignment]):
    def __init__(self, session: AsyncSession):
        super().__init__(KeyAssignment, session)

    async def revoke_all_for_key(self, key_id: UUID) -> None:
        await self.session.execute(
            update(KeyAssignment)
            .where(KeyAssignment.key_id == key_id)
            .values(
                desired_state=AssignmentDesiredState.absent.value,
                status="pending",
                last_error=None,
                last_applied_at=None,
                next_retry_at=None,
                attempts=0,
                op_version=KeyAssignment.op_version + 1,
            )
        )

    async def upsert_assignment_set_pending(
            self,
            *,
            key_id: UUID,
            node_id: UUID,
            desired_state: str,
    ) -> None:
        """
        Idempotent assign:
        - insert if missing
        - else update desired_state, reset error fields, set status=pending
        - op_version++ to signal reconciliation
        """
        stmt = insert(KeyAssignment).values(
            key_id=key_id,
            node_id=node_id,
            desired_state=desired_state,
            applied_state=AssignmentAppliedState.absent.value,
            status="pending",
            last_error=None,
            last_applied_at=None,
            next_retry_at=None,
            attempts=0,
        )
        on_conflict_stmt = stmt.on_conflict_do_update(
            index_elements=[KeyAssignment.key_id, KeyAssignment.node_id],
            set_={
                "desired_state": desired_state,
                "status": "pending",
                "last_error": None,
                "last_applied_at": None,
                "next_retry_at": None,
                "attempts": 0,
                "op_version": KeyAssignment.op_version + 1,
            }
        )

        await self.session.execute(on_conflict_stmt)

    async def list_for_node_with_keys_page(
            self,
            *,
            node_id: UUID,
            cursor: tuple[int, UUID] | None,
            limit: int,
    ) -> Sequence[tuple[KeyAssignment, VpnKey]]:
        """
        Stable pagination for node assignments.

        Cursor semantics: return rows strictly after (op_version, assignment_id) in
        order (op_version asc, assignment_id asc).
        """
        stmt = (
            select(KeyAssignment, VpnKey)
            .join(VpnKey, VpnKey.id == KeyAssignment.key_id)
            .where(
                KeyAssignment.node_id == node_id,
                KeyAssignment.is_active.is_(True),
                VpnKey.is_active.is_(True),
            )
        )
        if cursor is not None:
            op, aid = cursor
            stmt = stmt.where(
                or_(
                    KeyAssignment.op_version > op,
                    and_(KeyAssignment.op_version == op,
                         KeyAssignment.id > aid),
                )
            )

        stmt = stmt.order_by(KeyAssignment.op_version.asc(), KeyAssignment.id.asc()).limit(limit)

        res = await self.session.execute(stmt)
        return res.tuples().all()


async def get_key_assignment_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> KeyAssignmentRepository:
    return KeyAssignmentRepository(session)
