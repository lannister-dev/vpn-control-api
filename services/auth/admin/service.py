from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth.admin.constants import AdminRole
from services.auth.admin.crypto import (
    generate_csrf_token,
    generate_session_id,
    hash_password,
    hash_session_id,
    verify_password, verify_telegram_oidc_id_token,
)
from services.auth.admin.models import AdminSession, AdminUser
from services.auth.admin.repository import (
    AdminAuditRepository,
    AdminSessionRepository,
    AdminUserRepository,
)
from services.auth.admin.schemas import (
    AdminSessionCreate,
    AdminSessionOut,
    AdminUserCreateData,
    AdminUserListOut,
    AdminUserOut,
    AdminUserPasswordUpdateData,
    AdminUserSessionsOut,
    AdminUserUpdateData,
    LoginOut,
    SessionCheckOut,
)
from services.config import get_settings
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("admin-auth"))


class AdminAuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repository = AdminUserRepository(session)
        self.session_repository = AdminSessionRepository(session)
        self.audit_repository = AdminAuditRepository(session)

    async def login_password(
        self,
        *,
        username: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[LoginOut, str] | None:
        user = await self.user_repository.get_by_username(username)
        if user is None or not user.is_active:
            await self.audit_repository.log_event(
                action="login_failure",
                detail=f"username={username} reason=user_not_found",
                ip_address=ip_address,
            )
            return None

        if not user.password_hash:
            await self.audit_repository.log_event(
                action="login_failure",
                user_id=user.id,
                detail="reason=no_password_set",
                ip_address=ip_address,
            )
            return None

        if not verify_password(password, user.password_hash):
            await self.audit_repository.log_event(
                action="login_failure",
                user_id=user.id,
                detail="reason=bad_password",
                ip_address=ip_address,
            )
            return None

        return await self._create_session(
            user,
            ip_address=ip_address,
            user_agent=user_agent,
            auth_method="password",
        )

    async def login_telegram_oidc(
        self,
        *,
        code: str,
        redirect_uri: str,
        expected_nonce: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[LoginOut, str] | None:
        settings = get_settings()
        if not settings.admin_auth.telegram_login_enabled:
            return None
        if not settings.admin_auth.telegram_client_id or not settings.admin_auth.telegram_client_secret:
            return None

        token_data = self._exchange_telegram_code(
            code=code,
            redirect_uri=redirect_uri,
            client_id=settings.admin_auth.telegram_client_id,
            client_secret=settings.admin_auth.telegram_client_secret,
            token_url=settings.admin_auth.telegram_token_url,
        )
        if token_data is None:
            await self.audit_repository.log_event(
                action="login_failure",
                detail="reason=telegram_token_exchange_failed",
                ip_address=ip_address,
            )
            return None

        id_token = str(token_data.get("id_token") or "")
        if not id_token:
            await self.audit_repository.log_event(
                action="login_failure",
                detail="reason=telegram_missing_id_token",
                ip_address=ip_address,
            )
            return None

        claims = verify_telegram_oidc_id_token(
            id_token=id_token,
            client_id=settings.admin_auth.telegram_client_id,
            jwks_url=settings.admin_auth.telegram_jwks_url,
            issuer=settings.admin_auth.telegram_issuer,
            expected_nonce=expected_nonce,
        )
        if claims is None:
            await self.audit_repository.log_event(
                action="login_failure",
                detail="reason=telegram_oidc_invalid_id_token",
                ip_address=ip_address,
            )
            return None

        sub = claims.get("sub")
        try:
            telegram_id = int(sub)
        except (TypeError, ValueError):
            await self.audit_repository.log_event(
                action="login_failure",
                detail="reason=telegram_sub_invalid",
                ip_address=ip_address,
            )
            return None

        allowed_ids = settings.admin_auth.telegram_allowed_ids
        if allowed_ids and telegram_id not in allowed_ids:
            await self.audit_repository.log_event(
                action="login_failure",
                detail=f"reason=telegram_id_not_allowed telegram_id={telegram_id}",
                ip_address=ip_address,
            )
            return None

        user = await self.user_repository.get_by_telegram_id(telegram_id)
        if user is None or not user.is_active:
            await self.audit_repository.log_event(
                action="login_failure",
                detail=f"reason=telegram_user_not_found telegram_id={telegram_id}",
                ip_address=ip_address,
            )
            return None

        username = claims.get("preferred_username") or claims.get("username")
        if isinstance(username, str) and username and user.telegram_username != username:
            user.telegram_username = username

        return await self._create_session(
            user,
            ip_address=ip_address,
            user_agent=user_agent,
            auth_method="telegram_oidc",
        )

    async def validate_session(self, session_hash: str) -> tuple[AdminUser, AdminSession] | None:
        admin_session = await self.session_repository.get_valid_by_hash(session_hash)
        if admin_session is None:
            return None

        user = await self.user_repository.get_by_id(admin_session.user_id)
        if user is None or not user.is_active:
            return None

        return user, admin_session

    async def logout(
        self,
        *,
        session_hash: str,
        user_id: UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        await self.session_repository.delete_by_hash(session_hash)
        await self.audit_repository.log_event(
            action="logout",
            user_id=user_id,
            ip_address=ip_address,
        )

    async def check_session(self, session_hash: str | None) -> SessionCheckOut:
        if not session_hash:
            return SessionCheckOut(authenticated=False)

        result = await self.validate_session(session_hash)
        if result is None:
            return SessionCheckOut(authenticated=False)

        user, _ = result
        csrf = generate_csrf_token()
        return SessionCheckOut(
            authenticated=True,
            username=user.username,
            role=user.role,
            csrf_token=csrf,
        )

    async def create_user(
        self,
        *,
        username: str,
        password: str | None = None,
        telegram_id: int | None = None,
        role: AdminRole | str = AdminRole.viewer,
        creator_id: UUID | None = None,
        ip_address: str | None = None,
    ) -> AdminUser:
        role_enum = self._to_admin_role(role)
        password_hash = hash_password(password) if password else None
        user_in = AdminUserCreateData(
            username=username,
            role=role_enum,
            password_hash=password_hash,
            telegram_id=telegram_id,
        )
        user_data = user_in.model_dump(mode="json", exclude_none=True)
        user = await self.user_repository.create(user_data)
        await self.audit_repository.log_event(
            action="user_created",
            user_id=creator_id,
            detail=f"new_user={username} role={role_enum.value}",
            ip_address=ip_address,
        )
        return user

    async def list_users(
        self,
        *,
        search: str | None = None,
        role: AdminRole | str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminUserListOut:
        role_enum = self._to_admin_role(role) if role is not None else None
        users, total = await self.user_repository.list_users(
            search=search, role=role_enum.value if role_enum is not None else None, is_active=is_active,
            limit=limit, offset=offset,
        )
        return AdminUserListOut(
            items=[AdminUserOut.model_validate(u) for u in users],
            total=total, limit=limit, offset=offset,
        )

    async def update_user(
        self,
        *,
        target_user_id: UUID,
        role: AdminRole | str | None = None,
        is_active: bool | None = None,
        telegram_id: int | None = ...,
        telegram_username: str | None = ...,
        actor_id: UUID,
        ip_address: str | None = None,
    ) -> AdminUser:
        user = await self.user_repository.get_by_id(target_user_id)
        if user is None:
            raise ValueError("User not found")

        changes: dict = {}

        role_enum = self._to_admin_role(role) if role is not None else None

        if role_enum is not None and role_enum.value != user.role:
            if target_user_id == actor_id and role_enum != AdminRole.admin:
                raise PermissionError("Cannot demote your own role")
            changes["role"] = role_enum

        if is_active is not None and is_active != user.is_active:
            if not is_active:
                await self._guard_last_admin(target_user_id)
            changes["is_active"] = is_active

        if telegram_id is not ...:
            changes["telegram_id"] = telegram_id
        if telegram_username is not ...:
            changes["telegram_username"] = telegram_username

        if not changes:
            return user

        changes_in = AdminUserUpdateData.model_validate(changes)
        updated = await self.user_repository.update_by_id(
            target_user_id,
            changes_in.model_dump(mode="json", exclude_unset=True),
        )
        await self.audit_repository.log_event(
            action="user_updated",
            user_id=actor_id,
            detail=f"target={user.username} changes={list(changes.keys())}",
            ip_address=ip_address,
        )
        return updated

    async def reset_password(
        self,
        *,
        target_user_id: UUID,
        new_password: str,
        actor_id: UUID,
        ip_address: str | None = None,
    ) -> None:
        user = await self.user_repository.get_by_id(target_user_id)
        if user is None:
            raise ValueError("User not found")

        new_hash = hash_password(new_password)
        password_update = AdminUserPasswordUpdateData(password_hash=new_hash)
        await self.user_repository.update_by_id(
            target_user_id,
            password_update.model_dump(),
        )
        await self.audit_repository.log_event(
            action="password_reset",
            user_id=actor_id,
            detail=f"target={user.username}",
            ip_address=ip_address,
        )

    async def delete_user(
        self,
        *,
        target_user_id: UUID,
        actor_id: UUID,
        ip_address: str | None = None,
    ) -> None:
        user = await self.user_repository.get_by_id(target_user_id)
        if user is None:
            raise ValueError("User not found")

        if target_user_id == actor_id:
            raise PermissionError("Cannot delete yourself")

        await self._guard_last_admin(target_user_id)

        await self.session_repository.delete_by_user_id(target_user_id)
        await self.user_repository.delete_by_id(target_user_id)
        await self.audit_repository.log_event(
            action="user_deleted",
            user_id=actor_id,
            detail=f"deleted_user={user.username}",
            ip_address=ip_address,
        )

    async def get_user_sessions(
        self,
        *,
        target_user_id: UUID,
    ) -> AdminUserSessionsOut:
        sessions = await self.session_repository.list_by_user_id(target_user_id)
        return AdminUserSessionsOut(
            items=[AdminSessionOut.model_validate(s) for s in sessions],
            total=len(sessions),
        )

    async def revoke_user_sessions(
        self,
        *,
        target_user_id: UUID,
        actor_id: UUID,
        ip_address: str | None = None,
    ) -> int:
        user = await self.user_repository.get_by_id(target_user_id)
        if user is None:
            raise ValueError("User not found")

        count = await self.session_repository.delete_by_user_id(target_user_id)
        await self.audit_repository.log_event(
            action="sessions_revoked",
            user_id=actor_id,
            detail=f"target={user.username} count={count}",
            ip_address=ip_address,
        )
        return count

    async def _guard_last_admin(self, target_user_id: UUID) -> None:
        target = await self.user_repository.get_by_id(target_user_id)
        if target is None:
            return
        if target.role != AdminRole.admin.value or not target.is_active:
            return
        count = await self.user_repository.count_active_admins()
        if count <= 1:
            raise PermissionError(
                "Cannot deactivate or delete the last active admin"
            )

    async def _create_session(
        self,
        user: AdminUser,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        auth_method: Literal["password", "telegram_oidc"] = "password",
    ) -> tuple[LoginOut, str]:
        settings = get_settings()
        ttl = settings.admin_auth.session_ttl_sec
        session_id = generate_session_id()
        s_hash = hash_session_id(session_id)
        csrf = generate_csrf_token()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        session_in = AdminSessionCreate(
            user_id=user.id,
            session_hash=s_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        await self.session_repository.create(session_in.model_dump())

        await self.audit_repository.log_event(
            action="login_success",
            user_id=user.id,
            detail=f"method={auth_method}",
            ip_address=ip_address,
        )
        logger.info(
            "admin_login",
            username=user.username,
            role=user.role,
            ip=ip_address,
        )
        return (
            LoginOut(username=user.username, role=user.role, csrf_token=csrf),
            session_id,
        )

    @staticmethod
    def _exchange_telegram_code(
        *,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str,
        token_url: str,
    ) -> dict | None:
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        ).encode("utf-8")
        req = Request(
            token_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError):
            return None

    @staticmethod
    def _to_admin_role(role: AdminRole | str) -> AdminRole:
        if isinstance(role, AdminRole):
            return role
        return AdminRole(role)


def get_admin_auth_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> AdminAuthService:
    return AdminAuthService(session)
