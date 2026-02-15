from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status
from starlette.requests import Request

from services.auth.dependencies import node_auth, bootstrap_auth, admin_auth
from services.nodes.models import VpnNode
from services.nodes.schemas import NodeHeartbeatIn, NodeAgentInitialOut
from services.nodes.service import (
    NodeAgentService,
    VpnNodeService,
    get_vpn_node_service,
    get_node_agent_service
)
from services.vpn.keys.schemas import AssignmentReportIn, AssignmentPageOut
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
    "/assignments/page",
    response_model=AssignmentPageOut,
    summary="Get desired assignments page (stable cursor pagination)",
)
async def get_assignments_page(
        node: VpnNode = Depends(node_auth),
        cursor: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        service: NodeAgentService = Depends(get_node_agent_service),
) -> AssignmentPageOut:
    """
    Uses a stable cursor to avoid skipping when multiple rows share the same op_version.
    """
    try:
        items, next_cursor = await service.get_assignments_page_for_node(
            node=node,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AssignmentPageOut(items=items, next_cursor=next_cursor)


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


@router.post(
    "/nodes/{node_id}/drain",
    summary="Set node to draining",
    dependencies=[Depends(admin_auth)],
)
async def drain_node(
        node_id: UUID,
        service: VpnNodeService = Depends(get_vpn_node_service),
):
    node = await service.vpn_node_repository.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    await service.vpn_node_repository.update_by_id(
        node_id, {"is_draining": True}
    )
    return {"status": "draining"}


@router.post(
    "/nodes/{node_id}/enable",
    summary="Enable node (stop draining)",
    dependencies=[Depends(admin_auth)],
)
async def enable_node(
        node_id: UUID,
        service: VpnNodeService = Depends(get_vpn_node_service),
):
    node = await service.vpn_node_repository.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    await service.vpn_node_repository.update_by_id(
        node_id, {"is_draining": False, "is_enabled": True}
    )
    return {"status": "enabled"}
