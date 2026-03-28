from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.billing.schemas import PaymentProviderEnum
from services.bot_api.router import (
    bot_create_order,
    bot_get_order,
    bot_issue_subscription_link,
    bot_list_devices,
    bot_list_plans,
    bot_revoke_device,
    bot_sync_session,
)
from services.bot_api.schemas import (
    BotAction,
    BotDashboardState,
    BotDevicesOut,
    BotOrderActionOut,
    BotOrderCreateIn,
    BotOrderOut,
    BotPlanListOut,
    BotPlanOut,
    BotServiceHealth,
    BotServiceStatusOut,
    BotSessionOut,
    BotSessionSyncIn,
    BotSubscriptionLinkOut,
)


def _session_out() -> BotSessionOut:
    now = "2026-03-27T00:00:00Z"
    return BotSessionOut.model_validate(
        {
            "user": {
                "id": str(uuid4()),
                "telegram_id": 42,
                "username": "tester",
                "balance": "0",
                "is_active": True,
                "tag": "Test",
                "description": "Test User",
                "created_at": now,
                "updated_at": now,
            },
            "state": BotDashboardState.ACTIVE,
            "is_new_user": False,
            "subscription": None,
            "pending_order": None,
            "service": {
                "health": BotServiceHealth.OK,
                "message": "ok",
            },
            "available_actions": [BotAction.OPEN_HELP],
        }
    )


@pytest.mark.asyncio
async def test_bot_sync_session_contract():
    payload = BotSessionSyncIn(
        telegram_id=42,
        username="tester",
        first_name="Test",
        last_name="User",
    )
    out_expected = _session_out()
    service = SimpleNamespace(sync_session=AsyncMock(return_value=out_expected))

    out = await bot_sync_session(payload=payload, service=service)

    assert out == out_expected
    service.sync_session.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_bot_list_plans_contract():
    now = "2026-03-27T00:00:00Z"
    out_expected = BotPlanListOut(
        items=[
            BotPlanOut.model_validate(
                {
                    "id": str(uuid4()),
                    "name": "Start",
                    "description": "Test",
                    "traffic_limit_bytes": 0,
                    "reset_strategy": "NO_RESET",
                    "max_devices": 3,
                    "duration_days": 30,
                    "sort_order": 1,
                    "whitelist_enabled": False,
                    "price_rub": "199",
                    "is_active": True,
                    "is_current": False,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        ],
        total=1,
        current_plan_id=None,
    )
    service = SimpleNamespace(list_plans=AsyncMock(return_value=out_expected))

    out = await bot_list_plans(telegram_id=42, service=service)

    assert out == out_expected
    service.list_plans.assert_awaited_once_with(telegram_id=42)


@pytest.mark.asyncio
async def test_bot_create_order_contract():
    payload = BotOrderCreateIn(plan_id=uuid4(), provider=PaymentProviderEnum.CRYPTO)
    order = BotOrderOut.model_validate(
        {
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "plan_id": str(payload.plan_id),
            "amount_rub": "199",
            "provider": "crypto",
            "status": "pending",
            "external_id": "ext-1",
            "payment_url": "https://pay.example/1",
            "paid_at": None,
            "completed_at": None,
            "expires_at": "2026-03-27T01:00:00Z",
            "subscription_id": None,
            "created_at": "2026-03-27T00:00:00Z",
            "updated_at": "2026-03-27T00:00:00Z",
        }
    )
    out_expected = BotOrderActionOut(order=order, session=_session_out())
    service = SimpleNamespace(create_order=AsyncMock(return_value=out_expected))

    out = await bot_create_order(telegram_id=42, payload=payload, service=service)

    assert out == out_expected
    service.create_order.assert_awaited_once_with(telegram_id=42, payload=payload)


@pytest.mark.asyncio
async def test_bot_get_order_contract():
    order_id = uuid4()
    out_expected = BotOrderActionOut(
        order=BotOrderOut.model_validate(
            {
                "id": str(order_id),
                "user_id": str(uuid4()),
                "plan_id": None,
                "amount_rub": "199",
                "provider": "crypto",
                "status": "completed",
                "external_id": "ext-1",
                "payment_url": None,
                "paid_at": None,
                "completed_at": None,
                "expires_at": None,
                "subscription_id": None,
                "created_at": "2026-03-27T00:00:00Z",
                "updated_at": "2026-03-27T00:00:00Z",
            }
        ),
        session=_session_out(),
    )
    service = SimpleNamespace(get_order=AsyncMock(return_value=out_expected))

    out = await bot_get_order(telegram_id=42, order_id=order_id, service=service)

    assert out == out_expected
    service.get_order.assert_awaited_once_with(telegram_id=42, order_id=order_id)


@pytest.mark.asyncio
async def test_bot_list_devices_contract():
    out_expected = BotDevicesOut(session=_session_out(), items=[], total=0, active_total=0)
    service = SimpleNamespace(list_devices=AsyncMock(return_value=out_expected))

    out = await bot_list_devices(telegram_id=42, service=service)

    assert out == out_expected
    service.list_devices.assert_awaited_once_with(telegram_id=42)


@pytest.mark.asyncio
async def test_bot_revoke_device_contract():
    device_id = uuid4()
    out_expected = BotDevicesOut(session=_session_out(), items=[], total=0, active_total=0)
    service = SimpleNamespace(revoke_device=AsyncMock(return_value=out_expected))

    out = await bot_revoke_device(telegram_id=42, device_id=device_id, service=service)

    assert out == out_expected
    service.revoke_device.assert_awaited_once_with(telegram_id=42, device_id=device_id)


@pytest.mark.asyncio
async def test_bot_issue_subscription_link_contract():
    out_expected = BotSubscriptionLinkOut(
        subscription_url="https://example.com/sub/token",
        session=_session_out(),
    )
    service = SimpleNamespace(issue_subscription_link=AsyncMock(return_value=out_expected))

    out = await bot_issue_subscription_link(telegram_id=42, service=service)

    assert out == out_expected
    service.issue_subscription_link.assert_awaited_once_with(telegram_id=42)
