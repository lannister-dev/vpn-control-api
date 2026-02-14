import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.nodes.models import VpnNode
from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.nodes.schemas import (
    NodeAgentStateUpdate,
    NodeHeartbeatIn,
    NodeAgentInitialOut,
    VpnNodeUpdate,
    VpnNodeCreate
)
from services.vpn.keys.models import KeyAssignment, VpnKey
from services.vpn.keys.repository import KeyAssignmentRepository
from services.vpn.keys.schemas import (
    AssignmentReportIn,
    VpnProtocol,
    VpnTransport,
    AssignmentOut,
    AssignmentDesiredState,
    VpnKeyInternal,
    AssignmentStatus,
    AssignmentAppliedState
)
from shared.database.session import AsyncDatabase
from shared.redis.client import redis_client
from shared.metrics import (
    NODE_BOOTSTRAP_TOTAL,
    NODE_ASSIGNMENT_REPORT_TOTAL,
    ASSIGNMENT_CACHE_HIT_TOTAL,
    ASSIGNMENT_CACHE_MISS_TOTAL,
)
from shared.utils.logger import StructuredLogger

logger_node = StructuredLogger(logging.getLogger("node-service"))

_settings = get_settings()


class VpnNodeService:
    def __init__(self, session: AsyncSession):
        self.vpn_node_repository = (
            VpnNodeRepository(session)
        )
        self.node_agent_state_repository = (
            NodeAgentStateRepository(session)
        )
        self.key_assignment_repository = (
            KeyAssignmentRepository(session)
        )

    async def initial(self, *, source_ip: str) -> NodeAgentInitialOut:
        """
        Initial node identity bootstrap.

        - identity source: internal_wg_ip (source_ip)
        - idempotent
        - rotates auth token on every call
        """

        node = await self.vpn_node_repository.get_by_internal_ip(source_ip)

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        if node is None:
            create_schema = VpnNodeCreate(
                name=f"node-{source_ip.replace('.', '-')}",
                region="unknown",
                public_domain="",
                internal_wg_ip=source_ip,
                xray_api_port=10085,
                agent_port=9000,
                auth_token_hash=token_hash,
            )

            node = await self.vpn_node_repository.create(
                create_schema.model_dump()
            )
            NODE_BOOTSTRAP_TOTAL.labels(result="created").inc()
        else:
            update_schema = VpnNodeUpdate(
                auth_token_hash=token_hash
            )
            await self.vpn_node_repository.update_by_id(
                node.id,
                update_schema.model_dump(exclude_unset=True)
            )
            NODE_BOOTSTRAP_TOTAL.labels(result="rotated").inc()

        return NodeAgentInitialOut(
            node_id=str(node.id),
            node_auth_token=raw_token,
        )

    async def handle_heartbeat(
            self,
            node: VpnNode,
            payload: NodeHeartbeatIn,
    ) -> None:
        now = datetime.now(timezone.utc)

        state = NodeAgentStateUpdate(
            agent_version=payload.agent_version,
            is_healthy=payload.is_healthy,
            last_seen_at=now,
            details=payload.details.model_dump(),
        )
        await self.node_agent_state_repository.upsert(
            {
                "node_id": node.id,
                **state.model_dump(exclude_unset=True),
            }
        )
        if not payload.is_healthy and not node.is_draining:
            await self.vpn_node_repository.update_by_id(
                node.id,
                {"is_draining": True},
            )
            logger_node.info(
                "node set to draining due to unhealthy heartbeat",
                node_id=str(node.id),
            )

    async def report_assignment(
            self,
            node: VpnNode,
            assignment_id: UUID,
            payload: AssignmentReportIn,
    ) -> str:
        """
        Persist reconciliation result reported by node agent.
        Returns result status string.
        """
        lock_key = f"lock:assignment:{assignment_id}"

        acquired = await redis_client.client.set(
            lock_key, "1", ex=_settings.redis.assignment_lock_ttl, nx=True
        )
        if not acquired:
            NODE_ASSIGNMENT_REPORT_TOTAL.labels(status="skipped_lock").inc()
            return "skipped_lock"

        try:
            assignment = await self.key_assignment_repository.get_by_id(assignment_id)

            if assignment is None:
                raise HTTPException(status_code=404, detail="Assignment not found")

            if assignment.node_id != node.id:
                raise HTTPException(status_code=403, detail="Assignment does not belong to this node")

            if payload.op_version != assignment.op_version:
                NODE_ASSIGNMENT_REPORT_TOTAL.labels(status="skipped_stale").inc()
                return "skipped_stale"

            is_same = (
                    assignment.applied_state == payload.applied_state
                    and assignment.status == payload.status
                    and (assignment.last_error or None) == (payload.last_error or None)
                    and assignment.last_applied_at == payload.last_applied_at
            )
            if is_same:
                NODE_ASSIGNMENT_REPORT_TOTAL.labels(status="skipped_idempotent").inc()
                return "skipped_idempotent"

            update_data = payload.model_dump(exclude={"op_version"}, exclude_unset=True)

            await self.key_assignment_repository.update_by_id(
                assignment_id, update_data
            )
            if payload.status == AssignmentStatus.applied:
                state_update = NodeAgentStateUpdate(
                    last_sync_at=payload.last_applied_at,
                )
                await self.node_agent_state_repository.update_by_id(
                    node.id,
                    state_update.model_dump(exclude_unset=True),
                )
            report_status = "applied" if payload.status == AssignmentStatus.applied else "error"
            NODE_ASSIGNMENT_REPORT_TOTAL.labels(status=report_status).inc()
            # invalidate node assignments cache (optional but good)
            await redis_client.client.delete(f"node:{node.id}:assignments:v1")
            return report_status
        finally:
            try:
                await redis_client.client.delete(lock_key)
            except Exception:
                logger_node_agent.exception(
                    "failed to release redis lock", assignment_id=assignment_id
                )


async def get_vpn_node_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> VpnNodeService:
    return VpnNodeService(session)


logger_node_agent = StructuredLogger(logging.getLogger("node-agent-service"))


class NodeAgentService:
    def __init__(self, session: AsyncSession):
        self.key_assignment_repository = KeyAssignmentRepository(session)

    async def get_assignments_for_node(
            self,
            node: VpnNode,
    ) -> list[AssignmentOut]:
        """
        Returns desired-state assignments for a node.

        Business rules:
        - If key is revoked OR expired => effective desired_state = absent
        - Otherwise desired_state comes from KeyAssignment.desired_state
        """
        cache_key = f"node:{node.id}:assignments:v1"

        cached = await redis_client.client.get(cache_key)
        if cached:
            ASSIGNMENT_CACHE_HIT_TOTAL.inc()
            return [
                AssignmentOut.model_validate(item)
                for item in json.loads(cached)
            ]
        ASSIGNMENT_CACHE_MISS_TOTAL.inc()
        rows = await self.key_assignment_repository.list_for_node_with_keys(node_id=node.id)
        result = self._build_assignments(rows)

        await redis_client.client.setex(
            cache_key,
            _settings.redis.assignments_cache_ttl,
            json.dumps(
                [item.model_dump(mode="json") for item in result],
                ensure_ascii=False,
            ),
        )

        return result

    def _build_assignments(
            self,
            rows: Sequence[tuple[KeyAssignment, VpnKey]]
    ) -> list[AssignmentOut]:
        now = datetime.now(timezone.utc)
        result: list[AssignmentOut] = []

        for assignment, key in rows:
            key = VpnKeyInternal.model_validate(key, from_attributes=True)
            # effective desired-state overrides
            effective_desired = AssignmentDesiredState(assignment.desired_state)
            if key.is_revoked:
                effective_desired = AssignmentDesiredState.absent
            elif key.valid_until is not None:
                vu = key.valid_until
                if vu.tzinfo is None:
                    vu = vu.replace(tzinfo=timezone.utc)
                if vu <= now:
                    effective_desired = AssignmentDesiredState.absent

            # ---- applied_state ----
            if assignment.applied_state is None:
                applied_state = AssignmentAppliedState.unknown
            else:
                applied_state = AssignmentAppliedState(assignment.applied_state)

            # ---- status ----
            # If effective desired state diverged from applied state
            # (e.g. key expired or un-expired), signal the agent to reconcile
            # even though op_version hasn't changed.
            status = AssignmentStatus(assignment.status)
            if status == AssignmentStatus.applied and effective_desired.value != applied_state.value:
                status = AssignmentStatus.pending

            result.append(
                AssignmentOut(
                    id=assignment.id,
                    key_id=assignment.key_id,
                    op_version=assignment.op_version,
                    desired_state=effective_desired,
                    applied_state=applied_state,
                    status=status,

                    protocol=VpnProtocol(key.protocol),
                    transport=VpnTransport(key.transport),
                    client_id=key.client_id,

                    valid_until=key.valid_until,
                    traffic_limit_mb=key.traffic_limit_mb,
                    is_revoked=key.is_revoked,
                )
            )

        return result

async def get_node_agent_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> NodeAgentService:
    return NodeAgentService(session)