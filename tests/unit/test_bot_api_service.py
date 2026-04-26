from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.bot_api.schemas import (
    BotAction,
    BotOrderOut,
    BotServiceHealth,
    BotServiceStatusOut,
    BotSessionOut,
    BotUserOut,
)
from services.bot_api.schemas import BotDashboardState
from services.billing.schemas import OrderOut, OrderTypeEnum, PaymentProviderEnum
from services.bot_api.service import BotApiService


@pytest.fixture()
def service(async_session, redis_client):
    svc = BotApiService(async_session, redis_client)
    svc.settings = SimpleNamespace(
        subscriptions=SimpleNamespace(public_base_url="https://example.com/sub/"),
    )
    svc._require_user_by_telegram_id = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    svc._current_subscription = AsyncMock(
        return_value=SimpleNamespace(id=uuid4(), token="test_token_abc")
    )
    svc._classify_subscription = MagicMock(return_value=BotDashboardState.ACTIVE)
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
async def test_issue_subscription_link_returns_stable_url(service):
    out = await service.issue_subscription_link(telegram_id=42)

    assert out.subscription_url == "https://example.com/sub/test_token_abc"


@pytest.mark.asyncio
async def test_mark_traffic_warning_bumps_threshold(service):
    user_id = uuid4()
    sub_id = uuid4()
    service._require_user_by_telegram_id = AsyncMock(return_value=SimpleNamespace(id=user_id))
    sub = SimpleNamespace(id=sub_id, user_id=user_id, traffic_warning_threshold_pct=50)
    service.subscription_repository = AsyncMock()
    service.subscription_repository.get_by_id = AsyncMock(return_value=sub)
    service.subscription_repository.update_by_id = AsyncMock()

    await service.mark_traffic_warning(telegram_id=42, subscription_id=sub_id, threshold_pct=75)

    service.subscription_repository.update_by_id.assert_awaited_once_with(
        sub_id, {"traffic_warning_threshold_pct": 75}
    )


@pytest.mark.asyncio
async def test_mark_traffic_warning_noop_when_not_higher(service):
    user_id = uuid4()
    sub_id = uuid4()
    service._require_user_by_telegram_id = AsyncMock(return_value=SimpleNamespace(id=user_id))
    sub = SimpleNamespace(id=sub_id, user_id=user_id, traffic_warning_threshold_pct=75)
    service.subscription_repository = AsyncMock()
    service.subscription_repository.get_by_id = AsyncMock(return_value=sub)
    service.subscription_repository.update_by_id = AsyncMock()

    await service.mark_traffic_warning(telegram_id=42, subscription_id=sub_id, threshold_pct=50)
    await service.mark_traffic_warning(telegram_id=42, subscription_id=sub_id, threshold_pct=75)

    service.subscription_repository.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_traffic_warning_rejects_foreign_subscription(service):
    from fastapi import HTTPException

    sub_id = uuid4()
    service._require_user_by_telegram_id = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    sub = SimpleNamespace(id=sub_id, user_id=uuid4(), traffic_warning_threshold_pct=0)
    service.subscription_repository = AsyncMock()
    service.subscription_repository.get_by_id = AsyncMock(return_value=sub)

    with pytest.raises(HTTPException) as exc:
        await service.mark_traffic_warning(telegram_id=42, subscription_id=sub_id, threshold_pct=50)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_top_up_order_returns_amount_stars_for_stars_provider(service):
    user_id = uuid4()
    order = OrderOut(
        id=uuid4(),
        user_id=user_id,
        plan_id=None,
        amount_rub=Decimal("100"),
        provider="stars",
        status="pending",
        external_id="stars_test",
        payment_url=None,
        paid_at=None,
        completed_at=None,
        expires_at=datetime.now(timezone.utc),
        subscription_id=None,
        order_type=OrderTypeEnum.TOP_UP.value,
        device_slots_qty=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    service._require_user_by_telegram_id = AsyncMock(return_value=SimpleNamespace(id=user_id))
    service.billing_service.create_order = AsyncMock(return_value=order)

    out = await service.create_top_up_order(
        telegram_id=42,
        payload=SimpleNamespace(amount=Decimal("100"), provider=PaymentProviderEnum.STARS),
    )

    assert isinstance(out.order, BotOrderOut)
    assert out.order.amount_stars == 56
    service.billing_service.create_order.assert_awaited_once()
