from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from services.auth.dependencies import node_auth
from services.nodes.models import VpnNode
from services.nodes.repository import get_node_agent_state_repository, NodeAgentStateRepository
from services.nodes.schemas import NodeHeartbeatIn
from services.nodes.service import NodeService, NodeAgentService
from services.vpn.keys.repository import get_key_assignment_repository, KeyAssignmentRepository
from services.vpn.keys.schemas import AssignmentReportIn, AssignmentOut

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


@router.get(
    "/nodes/{node_id}/assignments",
    response_model=list[AssignmentOut],
    summary="Get desired assignments for node (desired-state)",
)
async def get_assignments(
        node_id: UUID,
        node: VpnNode = Depends(node_auth),
        repository: KeyAssignmentRepository = Depends(get_key_assignment_repository),
) -> list[AssignmentOut]:
    """
    Control-plane desired-state for NodeAgent reconciliation.

    Auth:
    - Authorization: Bearer <token>
    - X-Node-ID: <node_id>

    Returns:
    - list of assignments with key material required by Xray
    """
    if node.id != node_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to foreign node is forbidden",
        )
    return await NodeAgentService.get_assignments_for_node(
        node=node,
        repository=repository,
    )


@router.post(
    "/nodes/{node_id}/assignments/report",
    summary="Report assignment apply result"
)
async def report_assignment(
        assignment_id: UUID,
        payload: AssignmentReportIn,
        node: VpnNode = Depends(node_auth),
        repository: KeyAssignmentRepository = Depends(get_key_assignment_repository)

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
