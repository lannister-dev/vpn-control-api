"""HTTP endpoints for the 'Add Node' admin flow and the installer it serves."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from starlette import status

from services.auth.dependencies import (
    NodeInstallCredentials,
    admin_auth,
    node_install_auth,
)
from services.nodes.exceptions import (
    AdminNodeAlreadyBootstrappedError,
    AdminNodeCreateError,
    AdminNodeNotFoundError,
)
from services.nodes.installer import render_install_script
from services.nodes.schemas import (
    AdminNodeCreateIn,
    AdminNodeCreateOut,
    AdminNodeRotateBootstrapOut,
    NodeBootstrapCompleteIn,
    NodeBootstrapCompleteOut,
)
from services.nodes.service import VpnNodeService, get_vpn_node_service


admin_router = APIRouter(prefix="/admin/nodes", tags=["Admin Nodes"])
installer_router = APIRouter(prefix="/agent", tags=["Node Installer"])


@admin_router.post(
    "",
    response_model=AdminNodeCreateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pending VPN node + mint one-shot bootstrap token",
    dependencies=[Depends(admin_auth)],
)
async def admin_create_node(
    payload: AdminNodeCreateIn,
    service: VpnNodeService = Depends(get_vpn_node_service),
) -> AdminNodeCreateOut:
    try:
        return await service.admin_create_node(payload)
    except AdminNodeCreateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@admin_router.post(
    "/{node_id}/rotate-bootstrap-token",
    response_model=AdminNodeRotateBootstrapOut,
    summary="Rotate the bootstrap token for a pending node",
    dependencies=[Depends(admin_auth)],
)
async def admin_rotate_bootstrap_token(
    node_id: UUID,
    service: VpnNodeService = Depends(get_vpn_node_service),
) -> AdminNodeRotateBootstrapOut:
    try:
        return await service.admin_rotate_bootstrap_token(node_id)
    except AdminNodeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AdminNodeAlreadyBootstrappedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@installer_router.get(
    "/install.sh",
    response_class=PlainTextResponse,
    summary="Render the k3s-agent installer bash script for a pending node",
)
async def get_install_script(
    creds: NodeInstallCredentials = Depends(node_install_auth),
) -> PlainTextResponse:
    try:
        script = render_install_script(node=creds.node, raw_bootstrap_token=creds.raw_token)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return PlainTextResponse(
        content=script,
        media_type="text/x-shellscript",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline; filename=install.sh",
        },
    )


@installer_router.post(
    "/bootstrap-complete",
    response_model=NodeBootstrapCompleteOut,
    summary="Callback from the installer once k3s-agent joined the cluster",
)
async def bootstrap_complete(
    payload: NodeBootstrapCompleteIn | None = None,
    creds: NodeInstallCredentials = Depends(node_install_auth),
    service: VpnNodeService = Depends(get_vpn_node_service),
) -> NodeBootstrapCompleteOut:
    now = await service.mark_bootstrapped(creds.node)
    return NodeBootstrapCompleteOut(node_id=creds.node.id, bootstrapped_at=now)
