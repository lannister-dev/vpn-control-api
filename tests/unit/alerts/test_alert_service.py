from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.alerts.schemas import AlertLevel, AlertMessage
from services.alerts.service import AlertService
from services.config import AlertsConfig


def _build_service(*, telegram_enabled: bool) -> AlertService:
    config = AlertsConfig(
        telegram_enabled=telegram_enabled,
        telegram_bot_token="token",
        telegram_chat_id="chat",
        telegram_timeout_sec=5,
    )
    svc = AlertService(MagicMock(), config)
    svc.repo = MagicMock()
    svc.repo.find_active_by_dedup = AsyncMock(return_value=None)
    svc.repo.insert = AsyncMock()
    svc.repo.bump_existing = AsyncMock()
    svc.repo.resolve_active = AsyncMock(return_value=0)
    return svc


@pytest.mark.asyncio
async def test_send_returns_false_when_telegram_alerts_disabled():
    svc = _build_service(telegram_enabled=False)
    sent = await svc.send(
        AlertMessage(
            level=AlertLevel.warning,
            title="Test Alert",
            body="Body",
        )
    )
    assert sent is False


@pytest.mark.asyncio
async def test_send_probe_status_change_posts_message():
    svc = _build_service(telegram_enabled=True)

    captured = {}

    def _fake_post(payload):
        captured["chat_id"] = payload.chat_id
        captured["text"] = payload.text
        return True

    svc._post_telegram = _fake_post
    sent = await svc.send_probe_status_change(
        node_id=uuid4(),
        node_name="backend-fi-1",
        region="fi",
        source="ru-probe-1",
        is_reachable=False,
        checked_at=datetime.now(timezone.utc),
        error="timeout",
        route_id=uuid4(),
        transport_kind="reality",
        probe_kind="synthetic_vpn",
        target_host="203.0.113.10",
        target_port=443,
        error_phase="tcp",
    )

    assert sent is True
    assert captured["chat_id"] == "chat"
    assert "VPN Probe Status" in captured["text"]
    assert "FAILED" in captured["text"]
    assert "reality" in captured["text"]
    assert "203.0.113.10:443" in captured["text"]
    svc.repo.find_active_by_dedup.assert_awaited_once()
    svc.repo.insert.assert_awaited_once()
