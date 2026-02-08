from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from starlette.requests import Request

from services.auth.dependencies import node_auth, bootstrap_auth
from services.nodes.models import VpnNode
from services.nodes.schemas import NodeHeartbeatIn, NodeAgentInitialOut
from services.nodes.service import (
    NodeAgentService,
    VpnNodeService,
    get_vpn_node_service,
    get_node_agent_service
)
from services.vpn.keys.schemas import AssignmentReportIn, AssignmentOut
from shared.metrics import NODE_HEARTBEAT_TOTAL

router = APIRouter(prefix="/agent", tags=["Node Agent"])


@router.post(
    "/initial",
    response_model=NodeAgentInitialOut,
    summary="Agent bootstrap",
    dependencies=[Depends(bootstrap_auth)],
)
async def initial(wg_request: Request,
                  service: VpnNodeService = Depends(get_vpn_node_service)):
    """
    Initial node bootstrap. Requires bootstrap token.

    Auth: Authorization: Bearer <bootstrap_token>

    Idempotent: creates node on first call, rotates auth token on subsequent calls.
    Identity is derived from WireGuard source IP.
    """
    source_ip = wg_request.client.host

    if not source_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine source IP",
        )

    return await service.initial(source_ip=source_ip)


@router.post("/heartbeat", summary="Node agent heartbeat")
async def heartbeat(
        payload: NodeHeartbeatIn,
        node: VpnNode = Depends(node_auth),
        service: VpnNodeService = Depends(get_vpn_node_service)
):
    """
        Periodic heartbeat from NodeAgent.

        Auth:
        - Authorization: Bearer <token>
        - X-Node-ID: <node_id>
        """
    await service.handle_heartbeat(
        node=node, payload=payload,
    )
    NODE_HEARTBEAT_TOTAL.inc()
    return {"status": "ok"}


@router.get(
    "/assignments",
    response_model=list[AssignmentOut],
    summary="Get desired assignments for authenticated node",
)
async def get_assignments(
        node: VpnNode = Depends(node_auth),
        service: NodeAgentService= Depends(get_node_agent_service),
) -> list[AssignmentOut]:
    """
    Control-plane desired-state for NodeAgent reconciliation.

    Auth:
    - Authorization: Bearer <token>
    - X-Node-ID: <node_id>

    Returns:
    - list of assignments with key material required by Xray
    """
    return await service.get_assignments_for_node(node=node)


@router.post(
    "/assignments/{assignment_id}/report",
    summary="Report assignment apply result"
)
async def report_assignment(
        assignment_id: UUID,
        payload: AssignmentReportIn,
        node: VpnNode = Depends(node_auth),
        service: VpnNodeService = Depends(get_vpn_node_service),

):
    """
        NodeAgent reports result of applying assignment.
        """
    result = await service.report_assignment(
        node=node,
        assignment_id=assignment_id,
        payload=payload,
    )
    return {"status": result}
