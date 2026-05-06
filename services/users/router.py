from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.auth.dependencies import admin_auth
from services.users.exceptions import UserAlreadyExists, UserNotFound
from services.users.schemas import (
    UserCreateIn,
    UserDetailOut,
    UserListOut,
    UserOut,
    UserUpdateIn,
)
from services.users.service import UserService, get_user_service

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(admin_auth)])


@router.get(
    "",
    response_model=UserListOut,
    summary="List users with pagination and search",
)
async def list_users(
    search: str | None = Query(None, description="Search by username, telegram_id or UUID"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    tag: str | None = Query(None, description="Filter by exact tag"),
    has_debt: bool | None = Query(None, description="Filter users with balance < 0"),
    has_subscription: bool | None = Query(None, description="Filter users with/without subscriptions"),
    expiring_within_days: int | None = Query(None, ge=1, le=365, description="Filter users with active subscription expiring within N days"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: UserService = Depends(get_user_service),
):
    return await service.list_users(
        search=search,
        is_active=is_active,
        tag=tag,
        has_debt=has_debt,
        has_subscription=has_subscription,
        expiring_within_days=expiring_within_days,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{user_id}",
    response_model=UserDetailOut,
    summary="Get user details with subscription and key counts",
)
async def get_user(
    user_id: UUID,
    service: UserService = Depends(get_user_service),
):
    try:
        return await service.get_user_detail(user_id)
    except UserNotFound:
        raise HTTPException(status_code=404, detail="User not found")


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
)
async def create_user(
    data: UserCreateIn,
    service: UserService = Depends(get_user_service),
):
    try:
        return await service.create_user(data)
    except UserAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="Update user",
)
async def update_user(
    user_id: UUID,
    data: UserUpdateIn,
    service: UserService = Depends(get_user_service),
):
    try:
        return await service.update_user(user_id, data)
    except UserNotFound:
        raise HTTPException(status_code=404, detail="User not found")


@router.delete(
    "/{user_id}",
    response_model=UserOut,
    summary="Deactivate user (soft-delete)",
)
async def deactivate_user(
    user_id: UUID,
    service: UserService = Depends(get_user_service),
):
    try:
        return await service.deactivate_user(user_id)
    except UserNotFound:
        raise HTTPException(status_code=404, detail="User not found")
