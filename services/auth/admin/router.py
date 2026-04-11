from __future__ import annotations

from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status

from services.auth.admin.constants import (
    CSRF_COOKIE_NAME,
    TG_OIDC_NONCE_COOKIE_NAME,
    TG_OIDC_STATE_COOKIE_NAME,
    TG_OIDC_VERIFIER_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AdminRole,
)
from services.auth.admin.crypto import (
    generate_pkce_code_challenge,
    generate_pkce_code_verifier,
    hash_session_id,
)
from services.auth.admin.dependencies import require_role, verify_csrf
from services.auth.admin.models import AdminUser
from services.auth.admin.rate_limit import login_rate_limiter
from services.auth.admin.schemas import (
    AdminUserCreateIn,
    AdminUserListOut,
    AdminUserOut,
    AdminUserPasswordResetIn,
    AdminUserSessionsOut,
    AdminUserUpdateIn,
    LoginOut,
    PasswordLoginIn,
    SessionCheckOut,
)
from services.auth.admin.service import AdminAuthService, get_admin_auth_service
from services.auth.admin.utils import (
    clear_session_cookies,
    client_ip,
    set_csrf_cookie,
    set_session_cookie,
)
from services.config import get_settings

router = APIRouter(prefix="/auth/admin", tags=["Admin Auth"])

_LOGIN_PAGE_PATH = Path(__file__).with_name("login.html")


@router.get(
    "/login",
    response_class=HTMLResponse,
    include_in_schema=False,
    summary="Admin login page",
)
async def login_page() -> HTMLResponse:
    settings = get_settings()
    html = _LOGIN_PAGE_PATH.read_text(encoding="utf-8")
    html = html.replace(
        "{{TELEGRAM_LOGIN_ENABLED}}",
        "true" if settings.admin_auth.telegram_login_enabled else "false",
    )
    html = html.replace("{{TELEGRAM_OIDC_START_URL}}", "/api/v1/auth/admin/login/telegram/start")
    return HTMLResponse(content=html, status_code=200)


@router.post(
    "/login/password",
    response_model=LoginOut,
    status_code=status.HTTP_200_OK,
    summary="Login with username and password",
    description="Authenticates admin user with username/password credentials. "
                "Sets an HttpOnly session cookie on success.",
)
async def login_password(
    body: PasswordLoginIn,
    request: Request,
    response: Response,
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> LoginOut:
    ip = client_ip(request)
    if not login_rate_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )

    result = await service.login_password(
        username=body.username,
        password=body.password,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )
    if result is None:
        login_rate_limiter.record(ip)
        await service.session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    login_out, session_id = result
    settings = get_settings()
    set_session_cookie(
        response,
        session_id,
        settings.admin_auth.session_ttl_sec,
        secure=settings.admin_auth.session_cookie_secure,
    )
    set_csrf_cookie(
        response,
        login_out.csrf_token,
        secure=settings.admin_auth.session_cookie_secure,
    )
    return login_out


@router.get(
    "/login/telegram/start",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Start Telegram OIDC login flow",
)
async def login_telegram_start(
    request: Request,
):
    settings = get_settings()
    if not settings.admin_auth.telegram_login_enabled:
        raise HTTPException(status_code=404, detail="Telegram login disabled")
    if not settings.admin_auth.telegram_client_id:
        raise HTTPException(status_code=500, detail="Telegram OIDC client is not configured")

    redirect_uri = settings.admin_auth.telegram_redirect_uri or str(
        request.url_for("login_telegram_callback")
    )
    state = token_urlsafe(24)
    nonce = token_urlsafe(24)
    verifier = generate_pkce_code_verifier()
    challenge = generate_pkce_code_challenge(verifier)
    auth_url = (
        f"{settings.admin_auth.telegram_authorize_url}?"
        + urlencode(
            {
                "client_id": settings.admin_auth.telegram_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )
    response = RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    response.set_cookie(
        TG_OIDC_STATE_COOKIE_NAME,
        state,
        httponly=True,
        secure=settings.admin_auth.session_cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )
    response.set_cookie(
        TG_OIDC_NONCE_COOKIE_NAME,
        nonce,
        httponly=True,
        secure=settings.admin_auth.session_cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )
    response.set_cookie(
        TG_OIDC_VERIFIER_COOKIE_NAME,
        verifier,
        httponly=True,
        secure=settings.admin_auth.session_cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return response


@router.get(
    "/login/telegram/callback",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Telegram OIDC callback",
)
async def login_telegram_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    service: AdminAuthService = Depends(get_admin_auth_service),
):
    ip = client_ip(request)
    if error:
        await service.audit_repository.log_event(
            action="login_failure",
            detail=f"reason=telegram_callback_error error={error}",
            ip_address=ip,
        )
        await service.session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Telegram login error: {error_description or error}",
        )
    if not code or not state:
        await service.audit_repository.log_event(
            action="login_failure",
            detail="reason=telegram_callback_missing_params",
            ip_address=ip,
        )
        await service.session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OIDC callback parameters")
    if not login_rate_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
    cookie_state = request.cookies.get(TG_OIDC_STATE_COOKIE_NAME)
    cookie_nonce = request.cookies.get(TG_OIDC_NONCE_COOKIE_NAME)
    cookie_verifier = request.cookies.get(TG_OIDC_VERIFIER_COOKIE_NAME)
    if not cookie_state or state != cookie_state or not cookie_nonce or not cookie_verifier:
        login_rate_limiter.record(ip)
        await service.audit_repository.log_event(
            action="login_failure",
            detail="reason=telegram_invalid_oidc_state",
            ip_address=ip,
        )
        await service.session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OIDC state")

    settings = get_settings()
    redirect_uri = settings.admin_auth.telegram_redirect_uri or str(
        request.url_for("login_telegram_callback")
    )
    result = await service.login_telegram_oidc(
        code=code,
        redirect_uri=redirect_uri,
        expected_nonce=cookie_nonce,
        code_verifier=cookie_verifier,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )
    if result is None:
        login_rate_limiter.record(ip)
        await service.session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram login failed",
        )

    login_out, session_id = result
    response = RedirectResponse(url="/api/v1/admin/panel", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    set_session_cookie(
        response,
        session_id,
        settings.admin_auth.session_ttl_sec,
        secure=settings.admin_auth.session_cookie_secure,
    )
    set_csrf_cookie(
        response,
        login_out.csrf_token,
        secure=settings.admin_auth.session_cookie_secure,
    )
    response.delete_cookie(TG_OIDC_STATE_COOKIE_NAME, path="/")
    response.delete_cookie(TG_OIDC_NONCE_COOKIE_NAME, path="/")
    response.delete_cookie(TG_OIDC_VERIFIER_COOKIE_NAME, path="/")
    return response


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout and destroy session",
)
async def logout(
    request: Request,
    response: Response,
    _csrf_ok: None = Depends(verify_csrf),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> dict:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        session_hash = hash_session_id(session_id)
        result = await service.validate_session(session_hash)
        user_id = result[0].id if result else None
        await service.logout(
            session_hash=session_hash,
            user_id=user_id,
            ip_address=client_ip(request),
        )
    clear_session_cookies(response)
    return {"ok": True}


@router.get(
    "/session",
    response_model=SessionCheckOut,
    status_code=status.HTTP_200_OK,
    summary="Check current session",
    description="Returns session status. Used by the admin panel to verify "
                "authentication state on page load.",
)
async def check_session(
    request: Request,
    response: Response,
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> SessionCheckOut:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return SessionCheckOut(authenticated=False)

    session_hash = hash_session_id(session_id)
    out = await service.check_session(session_hash)

    if out.authenticated and out.csrf_token:
        set_csrf_cookie(
            response,
            out.csrf_token,
            secure=get_settings().admin_auth.session_cookie_secure,
        )

    return out


@router.post(
    "/users",
    response_model=AdminUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create admin user",
    description="Creates a new admin panel user. Requires admin role.",
)
async def create_admin_user(
    body: AdminUserCreateIn,
    request: Request,
    user: AdminUser = Depends(require_role(AdminRole.admin)),
    _csrf_ok: None = Depends(verify_csrf),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminUserOut:
    new_user = await service.create_user(
        username=body.username,
        password=body.password,
        telegram_id=body.telegram_id,
        role=body.role,
        creator_id=user.id,
        ip_address=client_ip(request),
    )
    return AdminUserOut.model_validate(new_user)


@router.get(
    "/users",
    response_model=AdminUserListOut,
    status_code=status.HTTP_200_OK,
    summary="List admin users",
    description="Returns a paginated list of admin users with optional filtering "
                "by role, active status, and free-text search. Requires admin role.",
)
async def list_admin_users(
    search: str | None = Query(None, max_length=128, description="Search by username or telegram"),
    role: AdminRole | None = Query(None, description="Filter by role"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Records to skip"),
    _user: AdminUser = Depends(require_role(AdminRole.admin)),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminUserListOut:
    return await service.list_users(
        search=search, role=role, is_active=is_active,
        limit=limit, offset=offset,
    )


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserOut,
    status_code=status.HTTP_200_OK,
    summary="Update admin user",
    description="Updates role, active status, or telegram info for an admin user. "
                "Cannot demote own role or deactivate the last admin.",
)
async def update_admin_user(
    user_id: UUID,
    body: AdminUserUpdateIn,
    request: Request,
    user: AdminUser = Depends(require_role(AdminRole.admin)),
    _csrf_ok: None = Depends(verify_csrf),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminUserOut:
    try:
        updated = await service.update_user(
            target_user_id=user_id,
            role=body.role,
            is_active=body.is_active,
            telegram_id=body.telegram_id if body.telegram_id is not None else ...,
            telegram_username=body.telegram_username if body.telegram_username is not None else ...,
            actor_id=user.id,
            ip_address=client_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return AdminUserOut.model_validate(updated)


@router.post(
    "/users/{user_id}/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset admin user password",
    description="Sets a new password for the specified admin user. Requires admin role.",
)
async def reset_admin_user_password(
    user_id: UUID,
    body: AdminUserPasswordResetIn,
    request: Request,
    user: AdminUser = Depends(require_role(AdminRole.admin)),
    _csrf_ok: None = Depends(verify_csrf),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> dict:
    try:
        await service.reset_password(
            target_user_id=user_id,
            new_password=body.new_password,
            actor_id=user.id,
            ip_address=client_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"ok": True}


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete admin user",
    description="Permanently deletes an admin user and all their sessions. "
                "Cannot delete yourself or the last active admin.",
)
async def delete_admin_user(
    user_id: UUID,
    request: Request,
    user: AdminUser = Depends(require_role(AdminRole.admin)),
    _csrf_ok: None = Depends(verify_csrf),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> dict:
    try:
        await service.delete_user(
            target_user_id=user_id,
            actor_id=user.id,
            ip_address=client_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return {"ok": True}


@router.get(
    "/users/{user_id}/sessions",
    response_model=AdminUserSessionsOut,
    status_code=status.HTTP_200_OK,
    summary="List active sessions for an admin user",
    description="Returns all active (non-expired) sessions for the specified admin user.",
)
async def list_user_sessions(
    user_id: UUID,
    _user: AdminUser = Depends(require_role(AdminRole.admin)),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminUserSessionsOut:
    return await service.get_user_sessions(target_user_id=user_id)


@router.post(
    "/users/{user_id}/revoke-sessions",
    status_code=status.HTTP_200_OK,
    summary="Revoke all sessions for an admin user",
    description="Destroys all active sessions for the specified admin user, "
                "forcing them to re-authenticate.",
)
async def revoke_user_sessions(
    user_id: UUID,
    request: Request,
    user: AdminUser = Depends(require_role(AdminRole.admin)),
    _csrf_ok: None = Depends(verify_csrf),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> dict:
    try:
        count = await service.revoke_user_sessions(
            target_user_id=user_id,
            actor_id=user.id,
            ip_address=client_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"ok": True, "revoked": count}
