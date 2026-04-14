from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from services.vpn.keys.models import VpnKey, KeyAssignment  # noqa: F401
from services.nodes.models import VpnNode  # noqa: F401
from services.users.models import User  # noqa: F401
from services.plans.models import Plan  # noqa: F401
from services.auth.admin.constants import (
    AdminRole,
    ROLE_HIERARCHY,
    SESSION_COOKIE_NAME,
    TG_OIDC_NONCE_COOKIE_NAME,
    TG_OIDC_STATE_COOKIE_NAME,
    TG_OIDC_VERIFIER_COOKIE_NAME,
)
from services.auth.admin.crypto import (
    generate_csrf_token,
    generate_pkce_code_challenge,
    generate_pkce_code_verifier,
    generate_session_id,
    hash_password,
    hash_session_id,
    verify_password,
)
from services.auth.admin.rate_limit import InMemoryRateLimiter
from services.auth.admin.router import login_telegram_start
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
from services.auth.admin.service import AdminAuthService


# ---------------------------------------------------------------------------
# Crypto tests
# ---------------------------------------------------------------------------

class TestCrypto:
    def test_hash_verify_password_roundtrip(self):
        pw = "mysecretpassword123"
        hashed = hash_password(pw)
        assert ":" in hashed
        assert verify_password(pw, hashed)

    def test_verify_password_wrong(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_verify_password_bad_format(self):
        assert not verify_password("test", "nocolon")

    def test_hash_password_different_salts(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # different salts
        assert verify_password("same", h1)
        assert verify_password("same", h2)

    def test_generate_session_id_length(self):
        sid = generate_session_id()
        assert len(sid) == 64  # 32 bytes hex

    def test_hash_session_id_deterministic(self):
        sid = "abc123"
        h1 = hash_session_id(sid)
        h2 = hash_session_id(sid)
        assert h1 == h2

    def test_generate_csrf_token(self):
        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert t1 != t2
        assert len(t1) == 32

    def test_pkce_verifier_and_challenge(self):
        verifier = generate_pkce_code_verifier()
        challenge = generate_pkce_code_challenge(verifier)
        assert verifier
        assert challenge
        assert "=" not in challenge


# ---------------------------------------------------------------------------
# Rate limiter tests
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allows_under_limit(self):
        rl = InMemoryRateLimiter(max_attempts=3, window_sec=60)
        assert rl.is_allowed("ip1")
        assert rl.is_allowed("ip1")
        assert rl.is_allowed("ip1")

    def test_blocks_over_limit(self):
        rl = InMemoryRateLimiter(max_attempts=2, window_sec=60)
        assert rl.is_allowed("ip1")
        assert rl.is_allowed("ip1")
        assert not rl.is_allowed("ip1")

    def test_different_keys_independent(self):
        rl = InMemoryRateLimiter(max_attempts=1, window_sec=60)
        assert rl.is_allowed("ip1")
        assert rl.is_allowed("ip2")
        assert not rl.is_allowed("ip1")

    def test_record_counts(self):
        rl = InMemoryRateLimiter(max_attempts=2, window_sec=60)
        rl.record("ip1")
        rl.record("ip1")
        assert not rl.is_allowed("ip1")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_password_login_in(self):
        body = PasswordLoginIn(username="admin", password="secret")
        assert body.username == "admin"

    def test_login_out(self):
        out = LoginOut(username="admin", role="admin", csrf_token="tok")
        assert out.ok is True

    def test_session_check_out_unauthenticated(self):
        out = SessionCheckOut(authenticated=False)
        assert out.username is None

    def test_admin_user_out_from_attributes(self):
        now = datetime.now(timezone.utc)
        obj = SimpleNamespace(
            id=uuid4(), username="admin", telegram_id=None,
            telegram_username=None, role="admin", is_active=True,
            created_at=now,
        )
        out = AdminUserOut.model_validate(obj)
        assert out.username == "admin"

    def test_admin_user_create_in_validation(self):
        body = AdminUserCreateIn(username="new_admin", password="longpassword", role="operator")
        assert body.role == "operator"

    def test_admin_user_create_in_role_validation(self):
        with pytest.raises(Exception):
            AdminUserCreateIn(username="x", password="longpassword", role="superadmin")


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------

class TestConstants:
    def test_admin_role_enum(self):
        assert AdminRole.admin.value == "admin"
        assert AdminRole.operator.value == "operator"
        assert AdminRole.viewer.value == "viewer"

    def test_role_hierarchy(self):
        assert ROLE_HIERARCHY["admin"] > ROLE_HIERARCHY["operator"]
        assert ROLE_HIERARCHY["operator"] > ROLE_HIERARCHY["viewer"]

    def test_has_value(self):
        assert AdminRole.has_value("admin")
        assert not AdminRole.has_value("superadmin")


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

def _make_admin_user(
    *,
    username="admin",
    password_hash=None,
    role="admin",
    is_active=True,
    telegram_id=None,
    telegram_username=None,
):
    return SimpleNamespace(
        id=uuid4(),
        username=username,
        password_hash=password_hash or hash_password("testpass"),
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        role=role,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestAdminAuthService:
    @pytest.fixture()
    def service(self, async_session):
        svc = AdminAuthService(async_session)
        svc.user_repository = AsyncMock()
        svc.session_repository = AsyncMock()
        svc.audit_repository = AsyncMock()
        return svc

    @patch("services.auth.admin.service.get_settings")
    async def test_login_password_success(self, mock_settings, service):
        mock_settings.return_value.admin_auth.session_ttl_sec = 3600
        user = _make_admin_user(password_hash=hash_password("correct"))
        service.user_repository.get_by_username.return_value = user
        service.session_repository.create.return_value = SimpleNamespace(id=uuid4())

        result = await service.login_password(
            username="admin", password="correct", ip_address="1.2.3.4"
        )
        assert result is not None
        login_out, session_id = result
        assert login_out.username == "admin"
        assert login_out.role == "admin"
        assert len(session_id) == 64

    async def test_login_password_user_not_found(self, service):
        service.user_repository.get_by_username.return_value = None
        result = await service.login_password(username="nope", password="x")
        assert result is None
        service.audit_repository.log_event.assert_awaited_once()

    async def test_login_password_wrong_password(self, service):
        user = _make_admin_user(password_hash=hash_password("correct"))
        service.user_repository.get_by_username.return_value = user
        result = await service.login_password(username="admin", password="wrong")
        assert result is None

    async def test_login_password_inactive_user(self, service):
        user = _make_admin_user(is_active=False)
        service.user_repository.get_by_username.return_value = user
        result = await service.login_password(username="admin", password="testpass")
        assert result is None

    async def test_login_password_no_password_set(self, service):
        user = _make_admin_user(password_hash=None)
        service.user_repository.get_by_username.return_value = user
        result = await service.login_password(username="admin", password="any")
        assert result is None

    async def test_validate_session_valid(self, service):
        user = _make_admin_user()
        session_obj = SimpleNamespace(
            id=uuid4(), user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        service.session_repository.get_valid_by_hash.return_value = session_obj
        service.user_repository.get_by_id.return_value = user

        result = await service.validate_session("somehash")
        assert result is not None
        assert result[0].username == "admin"

    async def test_validate_session_expired(self, service):
        service.session_repository.get_valid_by_hash.return_value = None
        result = await service.validate_session("badhash")
        assert result is None

    async def test_validate_session_user_inactive(self, service):
        user = _make_admin_user(is_active=False)
        session_obj = SimpleNamespace(
            id=uuid4(), user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        service.session_repository.get_valid_by_hash.return_value = session_obj
        service.user_repository.get_by_id.return_value = user
        result = await service.validate_session("hash")
        assert result is None

    async def test_logout(self, service):
        uid = uuid4()
        await service.logout(session_hash="hash", user_id=uid, ip_address="1.2.3.4")
        service.session_repository.delete_by_hash.assert_awaited_once_with("hash")
        service.audit_repository.log_event.assert_awaited_once()

    async def test_check_session_authenticated(self, service):
        user = _make_admin_user()
        session_obj = SimpleNamespace(
            id=uuid4(), user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        service.session_repository.get_valid_by_hash.return_value = session_obj
        service.user_repository.get_by_id.return_value = user

        out = await service.check_session("hash")
        assert out.authenticated is True
        assert out.username == "admin"
        assert out.csrf_token is not None

    async def test_check_session_no_hash(self, service):
        out = await service.check_session(None)
        assert out.authenticated is False

    async def test_check_session_invalid(self, service):
        service.session_repository.get_valid_by_hash.return_value = None
        out = await service.check_session("bad")
        assert out.authenticated is False

    @patch("services.auth.admin.service.get_settings")
    async def test_create_user(self, mock_settings, service):
        mock_settings.return_value.admin_auth.session_ttl_sec = 3600
        new_user = _make_admin_user(username="newuser", role="viewer")
        service.user_repository.create.return_value = new_user

        result = await service.create_user(
            username="newuser", password="longpassword", role="viewer",
            creator_id=uuid4(), ip_address="1.2.3.4",
        )
        assert result.username == "newuser"
        service.user_repository.create.assert_awaited_once()
        service.audit_repository.log_event.assert_awaited_once()

    @patch("services.auth.admin.service.get_settings")
    async def test_login_telegram_oidc_disabled(self, mock_settings, service):
        mock_settings.return_value.admin_auth.telegram_login_enabled = False
        result = await service.login_telegram_oidc(
            code="code",
            redirect_uri="https://admin.example/callback",
            expected_nonce="nonce",
            code_verifier="verifier",
        )
        assert result is None

    @patch("services.auth.admin.service.get_settings")
    async def test_login_telegram_oidc_user_not_found(self, mock_settings, service):
        mock_settings.return_value.admin_auth.telegram_login_enabled = True
        mock_settings.return_value.admin_auth.telegram_client_id = "client_id"
        mock_settings.return_value.admin_auth.telegram_client_secret = "secret"
        mock_settings.return_value.admin_auth.telegram_jwks_url = "https://example/jwks.json"
        mock_settings.return_value.admin_auth.telegram_issuer = "https://oauth.telegram.org"
        mock_settings.return_value.admin_auth.telegram_allowed_ids = ()
        mock_settings.return_value.admin_auth.telegram_oidc_proxy = ""
        service._exchange_telegram_code = AsyncMock(return_value=({"id_token": "jwt"}, None))
        service._verify_id_token = AsyncMock(return_value={"sub": "999", "preferred_username": "tg-user"})
        service.user_repository.get_by_telegram_id.return_value = None

        result = await service.login_telegram_oidc(
            code="code",
            redirect_uri="https://admin.example/callback",
            expected_nonce="nonce",
            code_verifier="verifier",
        )
        assert result is None

    @patch("services.auth.admin.service.get_settings")
    async def test_login_telegram_oidc_logs_exchange_error(self, mock_settings, service):
        mock_settings.return_value.admin_auth.telegram_login_enabled = True
        mock_settings.return_value.admin_auth.telegram_client_id = "client_id"
        mock_settings.return_value.admin_auth.telegram_client_secret = "secret"
        mock_settings.return_value.admin_auth.telegram_oidc_proxy = ""
        service._exchange_telegram_code = AsyncMock(return_value=(None, 'http_400:{"error":"invalid_grant"}'))

        result = await service.login_telegram_oidc(
            code="code",
            redirect_uri="https://admin.example/callback",
            expected_nonce="nonce",
            code_verifier="verifier",
            ip_address="1.2.3.4",
        )

        assert result is None
        service.audit_repository.log_event.assert_awaited_once()
        assert service.audit_repository.log_event.await_args.kwargs["detail"] == (
            'reason=telegram_token_exchange_failed error=http_400:{"error":"invalid_grant"}'
        )

    async def test_exchange_telegram_code_uses_pkce_and_basic_auth(self):
        import httpx

        captured = {}

        async def _handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = parse_qs(request.content.decode("utf-8"))
            captured["headers"] = dict(request.headers)
            return httpx.Response(200, json={"id_token": "jwt"})

        transport = httpx.MockTransport(_handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            with patch("services.auth.admin.service.httpx.AsyncClient") as mock_cls:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_cls.return_value = mock_ctx
                result, error = await AdminAuthService._exchange_telegram_code(
                    code="code123",
                    redirect_uri="https://api.example/callback",
                    code_verifier="verifier123",
                    client_id="client-id",
                    client_secret="client-secret",
                    token_url="https://oauth.telegram.org/token",
                )

        assert result == {"id_token": "jwt"}
        assert error is None
        assert captured["body"]["code"] == ["code123"]
        assert captured["body"]["code_verifier"] == ["verifier123"]
        assert "client_secret" not in captured["body"]
        assert captured["headers"]["authorization"] == (
            "Basic " + base64.b64encode(b"client-id:client-secret").decode("ascii")
        )

    async def test_exchange_telegram_code_returns_http_error_body(self):
        import httpx

        async def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        transport = httpx.MockTransport(_handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            with patch("services.auth.admin.service.httpx.AsyncClient") as mock_cls:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_cls.return_value = mock_ctx
                result, error = await AdminAuthService._exchange_telegram_code(
                    code="code123",
                    redirect_uri="https://api.example/callback",
                    code_verifier="verifier123",
                    client_id="client-id",
                    client_secret="client-secret",
                    token_url="https://oauth.telegram.org/token",
                )

        assert result is None
        assert "http_400" in error
        assert "invalid_grant" in error


class TestAdminAuthRouter:
    @patch("services.auth.admin.router.get_settings")
    async def test_login_telegram_start_sets_pkce(self, mock_settings):
        mock_settings.return_value.admin_auth.telegram_login_enabled = True
        mock_settings.return_value.admin_auth.telegram_client_id = "7010063753"
        mock_settings.return_value.admin_auth.telegram_redirect_uri = "https://api.example/callback"
        mock_settings.return_value.admin_auth.telegram_authorize_url = "https://oauth.telegram.org/auth"
        mock_settings.return_value.admin_auth.session_cookie_secure = True

        response = await login_telegram_start(request=MagicMock())

        parsed = urlparse(response.headers["location"])
        query = parse_qs(parsed.query)
        assert query["client_id"] == ["7010063753"]
        assert query["redirect_uri"] == ["https://api.example/callback"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["code_challenge"]

        set_cookie_headers = response.headers.getlist("set-cookie")
        assert any(TG_OIDC_STATE_COOKIE_NAME in header for header in set_cookie_headers)
        assert any(TG_OIDC_NONCE_COOKIE_NAME in header for header in set_cookie_headers)
        assert any(TG_OIDC_VERIFIER_COOKIE_NAME in header for header in set_cookie_headers)


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------

class TestAdminUserRepository:
    @pytest.fixture()
    def repo(self, async_session):
        from services.auth.admin.repository import AdminUserRepository
        return AdminUserRepository(async_session)

    async def test_get_by_username(self, repo):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        repo.session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_username("admin")
        assert result is None
        repo.session.execute.assert_awaited_once()

    async def test_get_by_telegram_id(self, repo):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        repo.session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_telegram_id(12345)
        assert result is None


class TestAdminSessionRepository:
    @pytest.fixture()
    def repo(self, async_session):
        from services.auth.admin.repository import AdminSessionRepository
        return AdminSessionRepository(async_session)

    async def test_get_valid_by_hash(self, repo):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        repo.session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_valid_by_hash("somehash")
        assert result is None

    async def test_delete_by_hash(self, repo):
        repo.session.execute = AsyncMock()
        await repo.delete_by_hash("hash")
        repo.session.execute.assert_awaited_once()

    async def test_delete_expired(self, repo):
        mock_result = MagicMock()
        mock_result.rowcount = 3
        repo.session.execute = AsyncMock(return_value=mock_result)
        count = await repo.delete_expired()
        assert count == 3

    async def test_delete_by_user_id(self, repo):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        repo.session.execute = AsyncMock(return_value=mock_result)
        count = await repo.delete_by_user_id(uuid4())
        assert count == 1


class TestAdminAuditRepository:
    @pytest.fixture()
    def repo(self, async_session):
        from services.auth.admin.repository import AdminAuditRepository
        return AdminAuditRepository(async_session)

    async def test_log_event(self, repo):
        repo.session.add = MagicMock()
        repo.session.flush = AsyncMock()
        event = await repo.log_event(
            action="login_success", user_id=uuid4(), ip_address="1.2.3.4"
        )
        assert event.action == "login_success"
        repo.session.add.assert_called_once()


# ---------------------------------------------------------------------------
# Admin user management (CRUD) service tests
# ---------------------------------------------------------------------------

class TestAdminUserManagement:
    @pytest.fixture()
    def service(self, async_session):
        svc = AdminAuthService(async_session)
        svc.user_repository = AsyncMock()
        svc.session_repository = AsyncMock()
        svc.audit_repository = AsyncMock()
        return svc

    # --- list ---

    async def test_list_users_returns_paginated(self, service):
        users = [_make_admin_user(username=f"u{i}") for i in range(3)]
        service.user_repository.list_users.return_value = (users, 3)

        result = await service.list_users(limit=10, offset=0)

        assert isinstance(result, AdminUserListOut)
        assert len(result.items) == 3
        assert result.total == 3
        assert result.limit == 10
        assert result.offset == 0

    async def test_list_users_with_filters(self, service):
        service.user_repository.list_users.return_value = ([], 0)

        result = await service.list_users(search="test", role="admin", is_active=True)

        assert result.total == 0
        service.user_repository.list_users.assert_awaited_once_with(
            search="test", role="admin", is_active=True, limit=50, offset=0,
        )

    async def test_list_users_empty(self, service):
        service.user_repository.list_users.return_value = ([], 0)
        result = await service.list_users()
        assert result.items == []
        assert result.total == 0

    # --- update ---

    async def test_update_user_role(self, service):
        user = _make_admin_user(username="target", role="viewer")
        actor_id = uuid4()
        service.user_repository.get_by_id.return_value = user
        updated = _make_admin_user(username="target", role="operator")
        service.user_repository.update_by_id.return_value = updated

        result = await service.update_user(
            target_user_id=user.id, role="operator", actor_id=actor_id,
        )

        assert result.role == "operator"
        service.audit_repository.log_event.assert_awaited_once()

    async def test_update_user_not_found(self, service):
        service.user_repository.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            await service.update_user(
                target_user_id=uuid4(), role="admin", actor_id=uuid4(),
            )

    async def test_update_cannot_demote_self(self, service):
        user = _make_admin_user(role="admin")
        service.user_repository.get_by_id.return_value = user

        with pytest.raises(PermissionError, match="Cannot demote your own role"):
            await service.update_user(
                target_user_id=user.id, role="viewer", actor_id=user.id,
            )

    async def test_update_deactivate_last_admin_blocked(self, service):
        user = _make_admin_user(role="admin", is_active=True)
        service.user_repository.get_by_id.return_value = user
        service.user_repository.count_active_admins.return_value = 1

        with pytest.raises(PermissionError, match="last active admin"):
            await service.update_user(
                target_user_id=user.id, is_active=False, actor_id=uuid4(),
            )

    async def test_update_deactivate_non_last_admin(self, service):
        user = _make_admin_user(role="admin", is_active=True)
        service.user_repository.get_by_id.return_value = user
        service.user_repository.count_active_admins.return_value = 2
        updated = _make_admin_user(role="admin", is_active=False)
        service.user_repository.update_by_id.return_value = updated

        result = await service.update_user(
            target_user_id=user.id, is_active=False, actor_id=uuid4(),
        )

        assert result.is_active is False

    async def test_update_no_changes(self, service):
        user = _make_admin_user(role="admin")
        service.user_repository.get_by_id.return_value = user

        result = await service.update_user(
            target_user_id=user.id, role="admin", actor_id=uuid4(),
        )

        assert result.username == "admin"
        service.user_repository.update_by_id.assert_not_awaited()

    # --- reset password ---

    @patch("services.auth.admin.service.hash_password")
    async def test_reset_password(self, mock_hash, service):
        mock_hash.return_value = "newhash"
        user = _make_admin_user()
        service.user_repository.get_by_id.return_value = user
        service.user_repository.update_by_id.return_value = user

        await service.reset_password(
            target_user_id=user.id, new_password="newpassword123",
            actor_id=uuid4(), ip_address="1.2.3.4",
        )

        service.user_repository.update_by_id.assert_awaited_once_with(
            user.id, {"password_hash": "newhash"},
        )
        service.audit_repository.log_event.assert_awaited_once()

    async def test_reset_password_user_not_found(self, service):
        service.user_repository.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            await service.reset_password(
                target_user_id=uuid4(), new_password="newpw12345",
                actor_id=uuid4(),
            )

    # --- delete ---

    async def test_delete_user_success(self, service):
        target = _make_admin_user(username="target", role="viewer")
        actor_id = uuid4()
        service.user_repository.get_by_id.return_value = target
        service.user_repository.count_active_admins.return_value = 1

        await service.delete_user(
            target_user_id=target.id, actor_id=actor_id,
        )

        service.session_repository.delete_by_user_id.assert_awaited_once()
        service.user_repository.delete_by_id.assert_awaited_once_with(target.id)
        service.audit_repository.log_event.assert_awaited_once()

    async def test_delete_user_not_found(self, service):
        service.user_repository.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            await service.delete_user(target_user_id=uuid4(), actor_id=uuid4())

    async def test_delete_self_blocked(self, service):
        user = _make_admin_user()
        service.user_repository.get_by_id.return_value = user

        with pytest.raises(PermissionError, match="Cannot delete yourself"):
            await service.delete_user(target_user_id=user.id, actor_id=user.id)

    async def test_delete_last_admin_blocked(self, service):
        target = _make_admin_user(role="admin", is_active=True)
        actor = _make_admin_user(role="admin")
        service.user_repository.get_by_id.return_value = target
        service.user_repository.count_active_admins.return_value = 1

        with pytest.raises(PermissionError, match="last active admin"):
            await service.delete_user(
                target_user_id=target.id, actor_id=actor.id,
            )

    async def test_delete_admin_when_multiple_admins(self, service):
        target = _make_admin_user(role="admin", is_active=True)
        actor = _make_admin_user(role="admin")
        service.user_repository.get_by_id.return_value = target
        service.user_repository.count_active_admins.return_value = 2

        await service.delete_user(
            target_user_id=target.id, actor_id=actor.id,
        )

        service.user_repository.delete_by_id.assert_awaited_once()

    # --- sessions ---

    async def test_get_user_sessions(self, service):
        sessions = [
            SimpleNamespace(
                id=uuid4(), user_id=uuid4(),
                ip_address="1.2.3.4", user_agent="Chrome",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                created_at=datetime.now(timezone.utc),
            )
        ]
        service.session_repository.list_by_user_id.return_value = sessions

        result = await service.get_user_sessions(target_user_id=uuid4())

        assert isinstance(result, AdminUserSessionsOut)
        assert len(result.items) == 1
        assert result.total == 1

    async def test_get_user_sessions_empty(self, service):
        service.session_repository.list_by_user_id.return_value = []

        result = await service.get_user_sessions(target_user_id=uuid4())

        assert result.items == []
        assert result.total == 0

    async def test_revoke_user_sessions(self, service):
        user = _make_admin_user()
        service.user_repository.get_by_id.return_value = user
        service.session_repository.delete_by_user_id.return_value = 3

        count = await service.revoke_user_sessions(
            target_user_id=user.id, actor_id=uuid4(), ip_address="1.2.3.4",
        )

        assert count == 3
        service.audit_repository.log_event.assert_awaited_once()

    async def test_revoke_sessions_user_not_found(self, service):
        service.user_repository.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            await service.revoke_user_sessions(
                target_user_id=uuid4(), actor_id=uuid4(),
            )


# ---------------------------------------------------------------------------
# New schema tests
# ---------------------------------------------------------------------------

class TestNewSchemas:
    def test_admin_user_update_in_valid(self):
        body = AdminUserUpdateIn(role="operator", is_active=False)
        assert body.role == "operator"
        assert body.is_active is False

    def test_admin_user_update_in_bad_role(self):
        with pytest.raises(Exception):
            AdminUserUpdateIn(role="superadmin")

    def test_admin_user_update_in_empty(self):
        body = AdminUserUpdateIn()
        assert body.role is None
        assert body.is_active is None

    def test_password_reset_in_validation(self):
        body = AdminUserPasswordResetIn(new_password="longenough")
        assert body.new_password == "longenough"

    def test_password_reset_in_too_short(self):
        with pytest.raises(Exception):
            AdminUserPasswordResetIn(new_password="short")

    def test_admin_user_list_out(self):
        out = AdminUserListOut(items=[], total=0, limit=50, offset=0)
        assert out.items == []

    def test_admin_user_sessions_out(self):
        out = AdminUserSessionsOut(items=[], total=0)
        assert out.total == 0


# ---------------------------------------------------------------------------
# Repository list/count tests
# ---------------------------------------------------------------------------

class TestAdminUserRepositoryExtended:
    @pytest.fixture()
    def repo(self, async_session):
        from services.auth.admin.repository import AdminUserRepository
        return AdminUserRepository(async_session)

    async def test_list_users_calls_session(self, repo):
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        repo.session.execute = AsyncMock(side_effect=[mock_count, mock_list])

        users, total = await repo.list_users(limit=10, offset=0)

        assert total == 0
        assert users == []
        assert repo.session.execute.await_count == 2

    async def test_list_users_with_filters(self, repo):
        mock_count = MagicMock()
        mock_count.scalar.return_value = 5
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        repo.session.execute = AsyncMock(side_effect=[mock_count, mock_list])

        users, total = await repo.list_users(
            role="admin", is_active=True, search="test", limit=20, offset=0,
        )

        assert total == 5

    async def test_count_active_admins(self, repo):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 2
        repo.session.execute = AsyncMock(return_value=mock_result)

        count = await repo.count_active_admins()

        assert count == 2


class TestAdminSessionRepositoryExtended:
    @pytest.fixture()
    def repo(self, async_session):
        from services.auth.admin.repository import AdminSessionRepository
        return AdminSessionRepository(async_session)

    async def test_list_by_user_id(self, repo):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        repo.session.execute = AsyncMock(return_value=mock_result)

        sessions = await repo.list_by_user_id(uuid4())

        assert sessions == []

    async def test_count_by_user_id(self, repo):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        repo.session.execute = AsyncMock(return_value=mock_result)

        count = await repo.count_by_user_id(uuid4())

        assert count == 3
