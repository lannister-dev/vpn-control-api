import json
import logging
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from fastapi import HTTPException
from services.config import get_settings
from services.nodes.models import VpnNode
from services.nodes.repository import NodeAgentStateRepository
from services.nodes.schemas import NodeAgentStateUpdate, NodeAgentStateCreate, NodeHeartbeatIn
from services.vpn.keys.models import KeyAssignment, VpnKey
from services.vpn.keys.repository import KeyAssignmentRepository
from services.vpn.keys.schemas import (
    AssignmentReportIn, VpnProtocol, VpnTransport,
    AssignmentOut, AssignmentDesiredState, VpnKeyInternal
)
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger

logger_node = StructuredLogger(logging.getLogger("node-service"))

_settings = get_settings()


class NodeService:
    @staticmethod
    async def handle_heartbeat(
            node: VpnNode,
            payload: NodeHeartbeatIn,
            repository: NodeAgentStateRepository,
    ) -> None:
        """
        Handle periodic heartbeat from node agent.

        - create agent state on first heartbeat
        - update agent state on subsequent heartbeats
        - idempotent
        """
        now = datetime.now(timezone.utc)
        state = await repository.get_by_id(node.id)

        if state is None:
            create_schema = NodeAgentStateCreate(
                node_id=node.id,
                agent_version=payload.agent_version,
                is_healthy=payload.is_healthy,
                last_seen_at=now,
                details=payload.details,
            )
            await repository.create(create_schema.model_dump())
            return

        update_schema = NodeAgentStateUpdate(
            agent_version=payload.agent_version,
            is_healthy=payload.is_healthy,
            last_seen_at=now,
            details=payload.details,
        )
        await repository.update_by_id(node.id, update_schema.model_dump(exclude_unset=True))

    @staticmethod
    async def report_assignment(
            node: VpnNode,
            assignment_id: UUID,
            payload: AssignmentReportIn,
            repository: KeyAssignmentRepository,
    ) -> None:
        """
        Persist reconciliation result reported by node agent.
        """
        lock_key = f"lock:assignment:{assignment_id}"

        acquired = await redis_client.client.set(
            lock_key, "1", ex=_settings.redis.assignment_lock_ttl, nx=True
        )
        if not acquired:
            return

        try:
            assignment = await repository.get_by_id(assignment_id)

            if assignment is None:
                raise HTTPException(status_code=404, detail="Assignment not found")

            if assignment.node_id != node.id:
                raise HTTPException(status_code=403, detail="Assignment does not belong to this node")

            update_data = payload.model_dump(exclude_unset=True)
            is_same = (
                    assignment.applied_state == payload.applied_state
                    and assignment.status == payload.status
                    and (assignment.last_error or None) == (payload.last_error or None)
                    and assignment.last_applied_at == payload.last_applied_at
            )
            if is_same:
                return
            await repository.update_by_id(assignment_id, update_data)
            # invalidate node assignments cache (optional but good)
            await redis_client.client.delete(f"node:{node.id}:assignments:v1")
        finally:
            try:
                await redis_client.client.delete(lock_key)
            except Exception:
                logger_node_agent.exception(
                    "failed to release redis lock", assignment_id=assignment_id
                )


logger_node_agent = StructuredLogger(logging.getLogger("node-agent-service"))


class NodeAgentService:
    @staticmethod
    async def get_assignments_for_node(
            node: VpnNode,
            repository: KeyAssignmentRepository,
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
            return [
                AssignmentOut.model_validate(item)
                for item in json.loads(cached)
            ]
        rows = await repository.list_for_node_with_keys(node_id=node.id)
        result = NodeAgentService._build_assignments(rows)

        await redis_client.client.setex(
            cache_key,
            _settings.redis.assignments_cache_ttl,
            json.dumps(
                [item.model_dump(mode="json") for item in result],
                ensure_ascii=False,
            ),
        )

        return result

    @staticmethod
    def _build_assignments(
            rows: Sequence[tuple[KeyAssignment, VpnKey]]
    ) -> list[AssignmentOut]:
        now = datetime.now(timezone.utc)
        result: list[AssignmentOut] = []

        for assignment, key in rows:
            key = VpnKeyInternal.model_validate(key, from_attributes=True)
            # effective desired-state overrides
            effective_desired = assignment.desired_state
            if key.is_revoked:
                effective_desired = AssignmentDesiredState.absent
            elif key.valid_until is not None:
                # ensure timezone-safe comparison
                vu = key.valid_until
                if vu.tzinfo is None:
                    vu = vu.replace(tzinfo=timezone.utc)
                if vu <= now:
                    effective_desired = AssignmentDesiredState.absent

            result.append(
                AssignmentOut(
                    id=assignment.id,
                    key_id=assignment.key_id,
                    desired_state=effective_desired,
                    applied_state=assignment.applied_state,
                    status=assignment.status,

                    protocol=VpnProtocol(key.protocol),
                    transport=VpnTransport(key.transport),
                    client_id=key.client_id,

                    valid_until=key.valid_until,
                    traffic_limit_mb=key.traffic_limit_mb,
                    is_revoked=key.is_revoked,
                )
            )

        return result
