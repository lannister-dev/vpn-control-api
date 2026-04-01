from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from services.bot_api.schemas import (
    BotAction,
    BotServiceHealth,
    BotServiceStatusOut,
    BotSessionOut,
    BotUserOut,
)
from services.bot_api.schemas import BotDashboardState
from services.bot_api.service import BotApiService


@pytest.fixture()
def service(async_session, redis_client):
    svc = BotApiService(async_session, redis_client)
    svc.settings = SimpleNamespace(
        subscriptions=SimpleNamespace(
            happ_crypto_api_url="https://crypto.happ.su/api-v2.php",
            happ_crypto_timeout_sec=5.0,
        )
    )
    svc._require_user_by_telegram_id = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    svc._current_subscription = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    svc._classify_subscription = MagicMock(return_value=BotDashboardState.ACTIVE)
    svc.subscription_service.rotate_token = AsyncMock(
        return_value=SimpleNamespace(subscription_url="https://example.com/sub/token")
    )
    now = datetime.now(timezone.utc)
    svc._build_session = AsyncMock(
        return_value=BotSessionOut(
            user=BotUserOut(
                id=uuid4(),
                telegram_id=42,
                username="tester",
                balance=Decimal("0"),
                is_active=True,
                tag=None,
                description=None,
                terms_accepted=False,
                terms_accepted_at=None,
                created_at=now,
                updated_at=now,
            ),
            state=BotDashboardState.ACTIVE,
            is_new_user=False,
            subscription=None,
            pending_order=None,
            service=BotServiceStatusOut(
                health=BotServiceHealth.OK,
                message="ok",
            ),
            available_actions=[BotAction.OPEN_CONNECT],
        )
    )
    return svc


@pytest.mark.asyncio
async def test_issue_subscription_link_returns_happ_crypt5_url(service):
    service._encrypt_subscription_url_for_happ = AsyncMock(
        return_value="happ://crypt5/abc123"
    )

    out = await service.issue_subscription_link(telegram_id=42)

    assert out.subscription_url == "happ://crypt5/abc123"
    service._encrypt_subscription_url_for_happ.assert_awaited_once_with(
        "https://example.com/sub/token"
    )


def test_parse_happ_crypto_response_accepts_plain_text_crypt5():
    response = httpx.Response(
        200,
        text="happ://crypt5/plain-text-value",
        headers={"content-type": "text/plain; charset=utf-8"},
    )

    out = BotApiService._parse_happ_crypto_response(response)

    assert out == "happ://crypt5/plain-text-value"


def test_parse_happ_crypto_response_accepts_json_payload():
    response = httpx.Response(
        200,
        json={"url": "happ://crypt5/json-value"},
        headers={"content-type": "application/json"},
    )

    out = BotApiService._parse_happ_crypto_response(response)

    assert out == "happ://crypt5/json-value"


def test_parse_happ_crypto_response_accepts_encrypted_link_payload():
    response = httpx.Response(
        200,
        json={"encrypted_link": "happ://crypt5/encrypted-link-value"},
        headers={"content-type": "application/json"},
    )

    out = BotApiService._parse_happ_crypto_response(response)

    assert out == "happ://crypt5/encrypted-link-value"


@pytest.mark.asyncio
async def test_encrypt_subscription_url_for_happ_falls_back_on_error(service):
    service.settings.subscriptions.happ_crypto_api_url = "https://crypto.happ.su/api-v2.php"

    class _BrokenClient:
        async def __aenter__(self):
            raise httpx.ConnectError("boom")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    from services.bot_api import service as bot_service_module

    original = bot_service_module.httpx.AsyncClient
    bot_service_module.httpx.AsyncClient = lambda timeout: _BrokenClient()
    try:
        out = await service._encrypt_subscription_url_for_happ("https://example.com/sub/token")
    finally:
        bot_service_module.httpx.AsyncClient = original

    assert out == "https://example.com/sub/token"
