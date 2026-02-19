from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status
from starlette.requests import Request

from services.auth.dependencies import node_auth, bootstrap_auth, admin_auth
from services.backend_peers.schemas import (
    BackendPeerGatewayPageOut,
    BackendPeerPageOut,
    BackendPeerReportIn,
    BackendPeerReportOut,
)
from services.backend_peers.service import (
    BackendPeerAgentService,
    get_backend_peer_agent_service,
    BackendPeerGatewayAgentService,
    get_backend_peer_gateway_agent_service,
)
from services.nodes.models import VpnNode
from services.nodes.schemas import NodeHeartbeatIn, NodeAgentInitialOut, NodeRoleUpdateIn, VpnNodeUpdate, NodeRole
from services.placements.schemas import PlacementPageOut, PlacementReportIn, PlacementReportOut
from services.placements.service import PlacementAgentService, get_placement_agent_service
from services.nodes.service import (
    VpnNodeService,
    get_vpn_node_service,
)
from shared.monitoring.metrics import NODE_HEARTBEAT_TOTAL

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
    "/placements/page",
    response_model=PlacementPageOut,
    summary="Get desired placements page (gateway agent)",
)
async def get_placements_page(
        node: VpnNode = Depends(node_auth),
        cursor: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        service: PlacementAgentService = Depends(get_placement_agent_service),
) -> PlacementPageOut:
    try:
        return await service.get_page_for_gateway(
            node=node,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/placements/{placement_id}/report",
    response_model=PlacementReportOut,
    summary="Report placement apply result (gateway agent)"
)
async def report_placement(
        placement_id: UUID,
        payload: PlacementReportIn,
        node: VpnNode = Depends(node_auth),
        service: PlacementAgentService = Depends(get_placement_agent_service),
):
    result = await service.report_for_gateway(
        node=node,
        placement_id=placement_id,
        payload=payload,
    )
    return PlacementReportOut(status=result)


@router.get(
    "/backend-peers/page",
    response_model=BackendPeerPageOut,
    summary="Get backend peer page (backend agent)",
)
async def get_backend_peers_page(
        node: VpnNode = Depends(node_auth),
        cursor: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        service: BackendPeerAgentService = Depends(get_backend_peer_agent_service),
) -> BackendPeerPageOut:
    try:
        return await service.get_page_for_backend(
            node=node,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/backend-peers/{peer_id}/report",
    response_model=BackendPeerReportOut,
    summary="Report backend peer apply result (backend agent)",
)
async def report_backend_peer(
        peer_id: UUID,
        payload: BackendPeerReportIn,
        node: VpnNode = Depends(node_auth),
        service: BackendPeerAgentService = Depends(get_backend_peer_agent_service),
):
    result = await service.report_for_backend(
        node=node,
        peer_id=peer_id,
        payload=payload,
    )
    return BackendPeerReportOut(status=result)


@router.get(
    "/gateway-peers/page",
    response_model=BackendPeerGatewayPageOut,
    summary="Get gateway peer page (gateway agent)",
)
async def get_gateway_peers_page(
        node: VpnNode = Depends(node_auth),
        cursor: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        service: BackendPeerGatewayAgentService = Depends(get_backend_peer_gateway_agent_service),
) -> BackendPeerGatewayPageOut:
    try:
        return await service.get_page_for_gateway(
            node=node,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


@router.post(
    "/nodes/{node_id}/role",
    summary="Set node role",
    dependencies=[Depends(admin_auth)],
)
async def set_node_role(
        node_id: UUID,
        payload: NodeRoleUpdateIn,
        service: VpnNodeService = Depends(get_vpn_node_service),
):
    node = await service.vpn_node_repository.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    await service.vpn_node_repository.update_by_id(
        node_id,
        VpnNodeUpdate(role=NodeRole(payload.role.value)).model_dump(exclude_unset=True),
    )
    return {"status": "role_updated", "role": payload.role.value}
