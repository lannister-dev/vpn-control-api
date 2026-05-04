from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from services.auth.dependencies import node_auth
from services.nodes.models import VpnNode
from services.wg.exceptions import WgMeshAddressPoolExhaustedError
from services.wg.schemas import WgRegisterIn, WgRegisterOut
from services.wg.service import WgMeshService, get_wg_mesh_service

router = APIRouter(prefix="/agent/wg", tags=["Node Agent WG"])


@router.post(
    "/register",
    response_model=WgRegisterOut,
    summary="Agent registers WG public key, gets internal mesh address + peer list",
)
async def register(
    payload: WgRegisterIn,
    node: VpnNode = Depends(node_auth),
    service: WgMeshService = Depends(get_wg_mesh_service),
) -> WgRegisterOut:
    try:
        return await service.register(node=node, payload=payload)
    except WgMeshAddressPoolExhaustedError as exc:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=str(exc),
        ) from exc
