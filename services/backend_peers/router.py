from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from services.auth.dependencies import admin_auth
from services.backend_peers.schemas import (
    BackendPeerEnsureIn,
    BackendPeerOut,
    BackendPeerUpsertIn,
)
from services.backend_peers.service import BackendPeerService, get_backend_peer_service

router = APIRouter(prefix="/backend-peers", tags=["Backend Peers"])


@router.post(
    "",
    response_model=BackendPeerOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_auth)],
    summary="Create or update backend peer (gateway <-> backend)",
)
async def upsert_backend_peer(
        payload: BackendPeerUpsertIn,
        service: BackendPeerService = Depends(get_backend_peer_service),
):
    return await service.upsert(payload)


@router.post(
    "/ensure",
    response_model=BackendPeerOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Ensure active backend peer pair exists",
)
async def ensure_backend_peer(
        payload: BackendPeerEnsureIn,
        service: BackendPeerService = Depends(get_backend_peer_service),
):
    return await service.ensure_active_pair(
        backend_node_id=payload.backend_node_id,
        gateway_node_id=payload.gateway_node_id,
    )


@router.get(
    "",
    response_model=list[BackendPeerOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="List backend peers",
)
async def list_backend_peers(
        backend_node_id: UUID | None = Query(default=None),
        gateway_node_id: UUID | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        service: BackendPeerService = Depends(get_backend_peer_service),
):
    return await service.list_peers(
        backend_node_id=backend_node_id,
        gateway_node_id=gateway_node_id,
        limit=limit,
    )
