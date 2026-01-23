from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from starlette import status

from services.nodes.models import VpnNode
from services.nodes.repository import NodeAgentStateRepository
from services.nodes.schemas import NodeAgentStateUpdate, NodeAgentStateCreate, NodeHeartbeatIn, AssignmentReportIn
from services.vpn.repository import KeyAssignmentRepository


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
        assignment = await repository.get_by_id(assignment_id)

        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )
        if assignment.node_id != node.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Assignment does not belong to this node",
            )

        update_data = payload.model_dump(exclude_unset=True)

        await repository.update_by_id(assignment_id, update_data)