from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from starlette import status
from starlette.requests import Request

from services.auth.dependencies import admin_auth, bootstrap_auth
from services.nodes.schemas import (
    AdminNodeUpdateIn,
    NodeAgentInitialOut,
    VpnNodeOut,
)
from services.nodes.service import (
    NodeBootstrapConflictError,
    VpnNodeService,
    get_vpn_node_service,
)

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
