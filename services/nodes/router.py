from uuid import UUID

from fastapi import APIRouter, Depends

from services.auth.dependencies import node_auth
from services.nodes.models import VpnNode
from services.nodes.repository import get_node_agent_state_repository, NodeAgentStateRepository
from services.nodes.schemas import NodeHeartbeatIn, AssignmentReportIn
from services.nodes.service import NodeService
from services.vpn.repository import get_key_assignments_repository, KeyAssignmentRepository

router = APIRouter(prefix="/agent", tags=["Node Agent"])


@router.post("/heartbeat", summary="Node agent heartbeat")
async def heartbeat(
        payload: NodeHeartbeatIn,
        node: VpnNode = Depends(node_auth),
        repository: NodeAgentStateRepository = Depends(get_node_agent_state_repository)
):
    """
        Periodic heartbeat from NodeAgent.

        Auth:
        - Authorization: Bearer <token>
        - X-Node-ID: <node_id>
        """
    await NodeService.handle_heartbeat(
        node=node, payload=payload, repository=repository
    )
    return {"status": "ok"}


@router.post(
    "/nodes/{node_id}/assignments/report",
    summary="Report assignment apply result"
)
async def report_assignment(
        assignment_id: UUID,
        payload: AssignmentReportIn,
        node: VpnNode = Depends(node_auth),
        repository: KeyAssignmentRepository = Depends(get_key_assignments_repository)

):
    """
        NodeAgent reports result of applying assignment.
        """
    await NodeService.report_assignment(
        node=node,
        assignment_id=assignment_id,
        payload=payload,
        repository=repository
    )
    return {"status": "ok"}
