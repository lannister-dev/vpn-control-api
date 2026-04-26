from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from starlette import status

from services.auth.admin.constants import (
    CSRF_HEADER_NAME,
    ROLE_HIERARCHY,
    SESSION_COOKIE_NAME,
    AdminRole,
)
from services.auth.admin.crypto import hash_session_id
from services.auth.admin.models import AdminUser
from services.auth.admin.service import AdminAuthService, get_admin_auth_service
from services.config import get_settings


async def get_current_admin(
    request: Request,
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminUser:
    settings = get_settings()
    if not settings.admin_auth.enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Admin auth is not enabled",
        )

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    session_hash = hash_session_id(session_id)
    result = await service.validate_session(session_hash)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )

    user, _ = result
    return user


def require_role(min_role: AdminRole):
    async def _check(user: AdminUser = Depends(get_current_admin)) -> AdminUser:
        user_level = ROLE_HIERARCHY.get(user.role, -1)
        required_level = ROLE_HIERARCHY.get(min_role.value, 999)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user
    return _check


async def verify_csrf(
    request: Request,
    _user: AdminUser = Depends(get_current_admin),
) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    csrf_token = request.headers.get(CSRF_HEADER_NAME)
    csrf_cookie = request.cookies.get("admin_csrf")
    if not csrf_token or not csrf_cookie:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing",
        )
    if csrf_token != csrf_cookie:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token mismatch",
        )
