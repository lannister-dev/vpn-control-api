from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from starlette import status
from starlette.requests import Request

from services.auth.dependencies import admin_auth, bootstrap_auth, node_auth
from services.nodes.models import VpnNode
from services.nodes.schemas import (
    AdminNodeUpdateIn,
    NodeAgentInitialOut,
    NodeHeartbeatIn,
    NodeRole,
    NodeRoleUpdateIn,
    NodeSyncReportIn,
    NodeSyncReportOut,
    NodeSyncReportStatus,
    VpnNodeOut,
    VpnNodeUpdate,
)
from services.placements.schemas import PlacementPageOut, PlacementReportIn, PlacementReportOut
from services.placements.service import PlacementAgentService, get_placement_agent_service
from services.nodes.service import (
    NodeBootstrapConflictError,
    VpnNodeService,
    get_vpn_node_service,
)
from shared.monitoring.metrics import NODE_HEARTBEAT_TOTAL, NODE_SYNC_REPORT_TOTAL

router = APIRouter(prefix="/agent", tags=["Node Agent"])


@router.post(
    "/initial",
    response_model=NodeAgentInitialOut,
    summary="Agent bootstrap",
    dependencies=[Depends(bootstrap_auth)],
)
async def initial(wg_request: Request,
                  x_node_key: str | None = Header(default=None, alias="X-Node-Key"),
                  x_agent_instance_id: UUID | None = Header(default=None, alias="X-Agent-Instance-ID"),
                  service: VpnNodeService = Depends(get_vpn_node_service)):
    """
    Initial node bootstrap. Requires bootstrap token.

    Auth: Authorization: Bearer <bootstrap_token>

    Idempotent: creates node on first call.
    Node identity is strict: X-Node-Key is required.
    Per-agent auth is strict: X-Agent-Instance-ID is required.
    Source IP is used as metadata (internal_wg_ip), not as identity fallback.
    """
    source_ip = wg_request.client.host

    if not source_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine source IP",
        )
    if not x_node_key or not x_node_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Node-Key header required",
        )
    if x_agent_instance_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Agent-Instance-ID header required",
        )

    try:
        return await service.initial(
            source_ip=source_ip,
            node_key=x_node_key,
            agent_instance_id=x_agent_instance_id,
        )
    except NodeBootstrapConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


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
        - X-Agent-Instance-ID: <agent_instance_id>
        - X-Node-ID: <node_id> (recommended, optional fallback exists)
        """
    await service.handle_heartbeat(
        node=node, payload=payload,
    )
    NODE_HEARTBEAT_TOTAL.inc()
    return {"status": "ok"}


@router.post(
    "/sync-report",
    response_model=NodeSyncReportOut,
    summary="Node agent sync report",
)
async def sync_report(
        payload: NodeSyncReportIn,
        node: VpnNode = Depends(node_auth),
        service: VpnNodeService = Depends(get_vpn_node_service),
) -> NodeSyncReportOut:
    updated = await service.handle_sync_report(node=node, payload=payload)
    report_status = NodeSyncReportStatus.accepted if updated else NodeSyncReportStatus.skipped
    NODE_SYNC_REPORT_TOTAL.labels(status=report_status.value).inc()

    return NodeSyncReportOut(status=report_status)


@router.get(
    "/placements/page",
    response_model=PlacementPageOut,
    summary="Get desired placements page",
)
async def get_placements_page(
        node: VpnNode = Depends(node_auth),
        cursor: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        service: PlacementAgentService = Depends(get_placement_agent_service),
) -> PlacementPageOut:
    try:
        return await service.get_page_for_backend(
            node=node,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/placements/{placement_id}/report",
    response_model=PlacementReportOut,
    summary="Report placement apply result (backend agent)"
)
async def report_placement(
        placement_id: UUID,
        payload: PlacementReportIn,
        node: VpnNode = Depends(node_auth),
        service: PlacementAgentService = Depends(get_placement_agent_service),
):
    result = await service.report_for_backend(
        node=node,
        placement_id=placement_id,
        payload=payload,
    )
    return PlacementReportOut(status=result)


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


@router.patch(
    "/nodes/{node_id}",
    response_model=VpnNodeOut,
    summary="Update node config by ID",
    dependencies=[Depends(admin_auth)],
)
async def update_node_by_id(
        node_id: UUID,
        payload: AdminNodeUpdateIn,
        service: VpnNodeService = Depends(get_vpn_node_service),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="Empty payload")
    node = await service.vpn_node_repository.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    updated = await service.vpn_node_repository.update_by_id(node_id, data)
    return updated


@router.patch(
    "/nodes/by-key/{node_key}",
    response_model=VpnNodeOut,
    summary="Update node config by node_key",
    dependencies=[Depends(admin_auth)],
)
async def update_node_by_key(
        node_key: str,
        payload: AdminNodeUpdateIn,
        service: VpnNodeService = Depends(get_vpn_node_service),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="Empty payload")
    node = await service.vpn_node_repository.get_by_node_key(node_key)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    updated = await service.vpn_node_repository.update_by_id(node.id, data)
    return updated
