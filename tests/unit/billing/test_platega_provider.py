from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.billing.exceptions import WebhookVerificationFailed
from services.billing.providers.platega import PlategaProvider


def _settings():
    return SimpleNamespace(
        billing=SimpleNamespace(
            platega_api_url="https://app.platega.io",
            platega_shop_id="merchant-123",
            platega_api_key="api-secret",
            platega_success_redirect_url="https://app.example.com/pay/success",
            platega_fail_redirect_url="https://app.example.com/pay/fail",
        )
    )


@pytest.mark.asyncio
async def test_create_payment_calls_platega_api(monkeypatch):
    from services.billing.providers import platega as provider_module

    monkeypatch.setattr(provider_module, "get_settings", _settings)
    provider = PlategaProvider()

    async def _mock_post(path, *, json=None, params=None, headers=None):
        assert path == "/transaction/process"
        assert json == {
            "paymentMethod": 2,
            "paymentDetails": {"amount": 299, "currency": "RUB"},
            "description": "Plan: Pro",
            "payload": "user-42",
            "return": "https://app.example.com/pay/success",
            "failedUrl": "https://app.example.com/pay/fail",
        }
        return {
            "transactionId": "txn-123",
            "redirect": "https://pay.platega.io/txn-123",
            "status": "PENDING",
        }

    monkeypatch.setattr(provider, "post", _mock_post)

    out = await provider.create_payment(
        order_id="user-42",
        amount_rub=299.0,
        description="Plan: Pro",
        payment_method=2,
    )

    assert out.external_id == "txn-123"
    assert out.payment_url == "https://pay.platega.io/txn-123"
    assert '"transactionId": "txn-123"' in (out.provider_meta or "")


@pytest.mark.asyncio
async def test_verify_webhook_accepts_confirmed_callback(monkeypatch):
    from services.billing.providers import platega as provider_module

    monkeypatch.setattr(provider_module, "get_settings", _settings)
    provider = PlategaProvider()
    request = SimpleNamespace(
        headers={
            "X-MerchantId": "merchant-123",
            "X-Secret": "api-secret",
        },
        json=AsyncMock(
            return_value={
                "id": "txn-123",
                "amount": 299,
                "currency": "RUB",
                "status": "CONFIRMED",
                "paymentMethod": 2,
            }
        ),
    )

    out = await provider.verify_webhook(request)

    assert out.external_id == "txn-123"
    assert out.amount_rub == 299.0
    assert out.should_fulfill is True
    assert out.provider_status == "CONFIRMED"


@pytest.mark.asyncio
async def test_verify_webhook_marks_canceled_callback_as_non_paid(monkeypatch):
    from services.billing.providers import platega as provider_module

    monkeypatch.setattr(provider_module, "get_settings", _settings)
    provider = PlategaProvider()
    request = SimpleNamespace(
        headers={
            "X-MerchantId": "merchant-123",
            "X-Secret": "api-secret",
        },
        json=AsyncMock(
            return_value={
                "id": "txn-123",
                "amount": 299,
                "currency": "RUB",
                "status": "CANCELED",
                "paymentMethod": 2,
            }
        ),
    )

    out = await provider.verify_webhook(request)

    assert out.should_fulfill is False
    assert out.provider_status == "CANCELED"


@pytest.mark.asyncio
async def test_verify_webhook_rejects_invalid_secret(monkeypatch):
    from services.billing.providers import platega as provider_module

    monkeypatch.setattr(provider_module, "get_settings", _settings)
    provider = PlategaProvider()
    request = SimpleNamespace(
        headers={
            "X-MerchantId": "merchant-123",
            "X-Secret": "wrong-secret",
        },
        json=AsyncMock(return_value={"id": "txn-123", "amount": 299, "status": "CONFIRMED"}),
    )

    with pytest.raises(WebhookVerificationFailed):
        await provider.verify_webhook(request)
