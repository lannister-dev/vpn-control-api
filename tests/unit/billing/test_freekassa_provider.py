from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from services.billing.exceptions import WebhookVerificationFailed
from services.billing.providers.freekassa import FreeKassaProvider


def _settings():
    return SimpleNamespace(
        billing=SimpleNamespace(
            freekassa_api_url="https://pay.fk.money/",
            freekassa_shop_id="12345",
            freekassa_secret_word_1="secret-1",
            freekassa_secret_word_2="secret-2",
            freekassa_currency="RUB",
        )
    )


@pytest.mark.asyncio
async def test_create_payment_builds_expected_url(monkeypatch):
    from services.billing.providers import freekassa as provider_module

    monkeypatch.setattr(provider_module, "get_settings", _settings)
    provider = FreeKassaProvider()

    out = await provider.create_payment(
        order_id="user-42",
        amount_rub=299.0,
        description="Plan: Pro",
    )

    parsed = urlparse(out.payment_url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "pay.fk.money"
    assert params["m"] == ["12345"]
    assert params["oa"] == ["299"]
    assert params["currency"] == ["RUB"]
    assert params["o"] == [out.external_id]
    assert params["us_order_id"] == ["user-42"]
    assert params["us_description"] == ["Plan: Pro"]
    assert "s" in params


@pytest.mark.asyncio
async def test_verify_webhook_accepts_valid_get_signature(monkeypatch):
    from services.billing.providers import freekassa as provider_module

    monkeypatch.setattr(provider_module, "get_settings", _settings)
    provider = FreeKassaProvider()
    sign = provider._sign_webhook(
        merchant_id="12345",
        amount="299",
        secret_word_2="secret-2",
        order_id="fk_order_1",
    )
    request = SimpleNamespace(
        method="GET",
        query_params={
            "MERCHANT_ID": "12345",
            "AMOUNT": "299",
            "MERCHANT_ORDER_ID": "fk_order_1",
            "SIGN": sign,
        },
        headers={},
    )

    out = await provider.verify_webhook(request)

    assert out.external_id == "fk_order_1"
    assert out.amount_rub == 299.0


@pytest.mark.asyncio
async def test_verify_webhook_rejects_invalid_signature(monkeypatch):
    from services.billing.providers import freekassa as provider_module

    monkeypatch.setattr(provider_module, "get_settings", _settings)
    provider = FreeKassaProvider()
    request = SimpleNamespace(
        method="GET",
        query_params={
            "MERCHANT_ID": "12345",
            "AMOUNT": "299",
            "MERCHANT_ORDER_ID": "fk_order_1",
            "SIGN": "bad-signature",
        },
        headers={},
    )

    with pytest.raises(WebhookVerificationFailed):
        await provider.verify_webhook(request)
