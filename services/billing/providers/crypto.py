from __future__ import annotations

import json
import logging

import jwt
from fastapi import Request

from services.billing.exceptions import ProviderError, WebhookVerificationFailed
from services.billing.providers.base import (
    PaymentProvider,
    ProviderCreateResult,
    WebhookResult,
)
from services.config import get_settings
from shared.api import BaseApiClient, HttpError

log = logging.getLogger("billing.crypto")


class CryptoProvider(BaseApiClient, PaymentProvider):
    """CryptoCloud v2 payment provider.

    Docs: https://docs.cryptocloud.plus/ru/api-reference-v2
    """

    def __init__(self) -> None:
        cfg = get_settings().billing
        if not cfg.crypto_api_key or not cfg.crypto_shop_id:
            raise ProviderError("CryptoCloud API key or shop_id not configured")

        super().__init__(
            base_url=cfg.crypto_api_url,
            headers={
                "Authorization": f"Token {cfg.crypto_api_key}",
                "Content-Type": "application/json",
            },
            timeout_s=15.0,
        )
        self.shop_id = cfg.crypto_shop_id
        self.webhook_secret = cfg.crypto_webhook_secret

    async def create_payment(
        self,
        *,
        order_id: str,
        amount_rub: float,
        description: str,
        payment_method: int | None = None,
    ) -> ProviderCreateResult:
        try:
            data = await self.post(
                "/invoice/create",
                json={
                    "shop_id": self.shop_id,
                    "amount": amount_rub,
                    "currency": "RUB",
                    "order_id": order_id,
                },
            )
        except HttpError as exc:
            log.error("cryptocloud_create_failed status=%d body=%s", exc.status, exc.body)
            raise ProviderError(
                f"CryptoCloud returned {exc.status}: {exc.body}",
                upstream_status=exc.status,
            ) from exc

        if data.get("status") != "success":
            raise ProviderError(f"CryptoCloud error: {data}")

        result = data["result"]
        return ProviderCreateResult(
            external_id=result["uuid"],
            payment_url=result["link"],
            provider_meta=json.dumps(result),
        )

    async def verify_webhook(self, request: Request) -> WebhookResult:
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)

        token = body.get("token")
        if not token:
            raise WebhookVerificationFailed("Missing token in postback")

        if not self.webhook_secret:
            raise WebhookVerificationFailed("Webhook secret not configured")

        try:
            jwt.decode(token, self.webhook_secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise WebhookVerificationFailed("Postback token expired")
        except jwt.InvalidTokenError as exc:
            raise WebhookVerificationFailed(f"Invalid postback token: {exc}")

        invoice_info = body.get("invoice_info") or {}
        invoice_uuid = invoice_info.get("uuid") or body.get("uuid") or body.get("invoice_uuid")
        invoice_id = body.get("invoice_id")
        if not invoice_uuid and not invoice_id:
            raise WebhookVerificationFailed("Missing invoice_id in postback")

        external_id = (
            str(invoice_uuid)
            if invoice_uuid
            else (str(invoice_id) if str(invoice_id).startswith("INV-") else f"INV-{invoice_id}")
        )

        amount_raw = (
            invoice_info.get("amount_in_fiat")
            or invoice_info.get("amount")
            or body.get("amount_in_fiat")
            or body.get("amount")
            or 0
        )
        try:
            amount_rub = float(amount_raw)
        except (TypeError, ValueError):
            amount_rub = 0.0

        status_raw = str(
            invoice_info.get("status")
            or body.get("status")
            or body.get("invoice_status")
            or ""
        ).strip().upper()
        should_fulfill = status_raw in ("", "PAID", "OVERPAID", "SUCCESS")

        return WebhookResult(
            external_id=external_id,
            amount_rub=amount_rub,
            provider_meta=json.dumps(body, default=str),
            should_fulfill=should_fulfill,
            provider_status=status_raw or None,
        )
