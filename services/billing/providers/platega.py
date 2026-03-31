from __future__ import annotations

import json
import uuid

from fastapi import Request

from services.billing.exceptions import ProviderError, WebhookVerificationFailed
from services.billing.providers.base import (
    PaymentProvider,
    ProviderCreateResult,
    WebhookResult,
)
from services.config import get_settings


class PlategaProvider(PaymentProvider):
    def __init__(self) -> None:
        cfg = get_settings().billing
        self.api_url = cfg.platega_api_url
        self.shop_id = cfg.platega_shop_id
        self.api_key = cfg.platega_api_key
        self.webhook_secret = cfg.platega_webhook_secret

    async def create_payment(
        self, *, order_id: str, amount_rub: float, description: str
    ) -> ProviderCreateResult:
        # TODO: replace with real Platega API call (SBP/cards)
        external_id = f"platega_{uuid.uuid4().hex[:16]}"
        payment_url = f"{self.api_url}/pay/{external_id}"
        return ProviderCreateResult(
            external_id=external_id,
            payment_url=payment_url,
            provider_meta=json.dumps({"order_id": order_id, "shop_id": self.shop_id}),
        )

    async def verify_webhook(self, request: Request) -> WebhookResult:
        # TODO: implement Platega HMAC signature verification
        body = await request.json()
        external_id = body.get("external_id")
        amount = body.get("amount")
        if not external_id or amount is None:
            raise WebhookVerificationFailed("Missing required fields")
        return WebhookResult(
            external_id=external_id,
            amount_rub=float(amount),
            provider_meta=json.dumps(body),
        )
