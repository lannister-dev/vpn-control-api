from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from services.auth.dependencies import admin_auth, relay_auth
from services.entry.schemas import (
    EntryBackendAssignIn,
    EntryBackendAssignmentOut,
    EntryBackendUpdateIn,
    RelayPoolOut,
)
from services.entry.service import (
    BackendNotFoundError,
    EntryNotFoundError,
    EntryRoleError,
    EntryService,
    EntryZoneMismatchError,
    get_entry_service,
)

router = APIRouter(prefix="/entry", tags=["Entry Relay"])


@router.get(
    "/{entry_id}/backends",
    response_model=RelayPoolOut,
    summary="Relay pool for a given entry node (consumed by the Go relay binary)",
    dependencies=[Depends(relay_auth)],
)
async def get_relay_pool(
    entry_id: UUID,
    service: EntryService = Depends(get_entry_service),
):
    try:
        return await service.get_relay_pool(entry_id)
    except EntryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EntryRoleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{entry_id}/assignments",
    response_model=list[EntryBackendAssignmentOut],
    summary="List backend assignments for an entry node",
    dependencies=[Depends(admin_auth)],
)
async def list_assignments(
    entry_id: UUID,
    service: EntryService = Depends(get_entry_service),
):
    try:
        return await service.list_assignments(entry_id)
    except EntryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EntryRoleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{entry_id}/assignments",
    response_model=EntryBackendAssignmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a backend to an entry node's relay pool (idempotent by pair)",
    dependencies=[Depends(admin_auth)],
)
async def assign_backend(
    entry_id: UUID,
    payload: EntryBackendAssignIn,
    service: EntryService = Depends(get_entry_service),
):
    try:
        return await service.assign_backend(entry_id, payload)
    except EntryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BackendNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EntryZoneMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EntryRoleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch(
    "/{entry_id}/assignments/{backend_id}",
    response_model=EntryBackendAssignmentOut,
    summary="Update weight/enabled on an existing entry→backend assignment",
    dependencies=[Depends(admin_auth)],
)
async def update_assignment(
    entry_id: UUID,
    backend_id: UUID,
    payload: EntryBackendUpdateIn,
    service: EntryService = Depends(get_entry_service),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty payload")
    updated = await service.update_assignment(entry_id, backend_id, payload)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return updated


@router.delete(
    "/{entry_id}/assignments/{backend_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a backend from an entry node's relay pool",
    dependencies=[Depends(admin_auth)],
)
async def remove_assignment(
    entry_id: UUID,
    backend_id: UUID,
    service: EntryService = Depends(get_entry_service),
):
    removed = await service.remove_assignment(entry_id, backend_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return None
