from __future__ import annotations

import hmac
import json
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Request

from services.billing.exceptions import ProviderError, WebhookVerificationFailed
from services.billing.providers.base import (
    PaymentProvider,
    ProviderCreateResult,
    WebhookResult,
)
from services.billing.schemas import PlategaPaymentMethodEnum
from services.config import get_settings
from shared.api import BaseApiClient, HttpError


class PlategaProvider(BaseApiClient, PaymentProvider):
    def __init__(self) -> None:
        cfg = get_settings().billing
        self.api_url = cfg.platega_api_url
        self.shop_id = cfg.platega_shop_id
        self.api_key = cfg.platega_api_key
        self.success_redirect_url = cfg.platega_success_redirect_url
        self.fail_redirect_url = cfg.platega_fail_redirect_url

        if not self.shop_id:
            raise ProviderError("Platega shop_id not configured")
        if not self.api_key:
            raise ProviderError("Platega API key not configured")

        super().__init__(
            base_url=self.api_url,
            headers={
                "Content-Type": "application/json",
                "X-MerchantId": self.shop_id,
                "X-Secret": self.api_key,
            },
            timeout_s=15.0,
        )

    async def create_payment(
        self,
        *,
        order_id: str,
        amount_rub: float,
        description: str,
        payment_method: PlategaPaymentMethodEnum | int | None = None,
    ) -> ProviderCreateResult:
        if payment_method is None or int(payment_method) <= 0:
            raise ProviderError("Platega payment_method is required")
        payment_method_id = int(payment_method)
        payload = {
            "paymentMethod": payment_method_id,
            "paymentDetails": {
                "amount": self._normalize_amount(amount_rub),
                "currency": "RUB",
            },
            "description": description,
            "payload": order_id,
        }
        if self.success_redirect_url:
            payload["return"] = self.success_redirect_url
        if self.fail_redirect_url:
            payload["failedUrl"] = self.fail_redirect_url

        try:
            data = await self.post("/transaction/process", json=payload)
        except HttpError as exc:
            raise ProviderError(
                f"Platega returned {exc.status}: {exc.body}",
                upstream_status=exc.status,
            ) from exc

        external_id = str(data.get("transactionId") or data.get("id") or "").strip()
        payment_url = str(
            data.get("redirect") or data.get("payformSuccessUrl") or ""
        ).strip()
        if not external_id:
            raise ProviderError(f"Platega response missing transaction id: {data}")
        if not payment_url:
            raise ProviderError(f"Platega response missing redirect url: {data}")

        return ProviderCreateResult(
            external_id=external_id,
            payment_url=payment_url,
            provider_meta=json.dumps(
                {
                    "payment_method": payment_method_id,
                    "response": data,
                },
                default=str,
            ),
        )

    async def verify_webhook(self, request: Request) -> WebhookResult:
        merchant_id = (request.headers.get("X-MerchantId") or "").strip()
        secret = (request.headers.get("X-Secret") or "").strip()
        if not merchant_id or not secret:
            raise WebhookVerificationFailed("Missing Platega webhook headers")
        if merchant_id != self.shop_id:
            raise WebhookVerificationFailed("Platega merchant_id mismatch")
        if not hmac.compare_digest(secret, self.api_key):
            raise WebhookVerificationFailed("Invalid Platega webhook secret")

        body = await request.json()
        if not isinstance(body, dict):
            raise WebhookVerificationFailed("Invalid Platega webhook payload")

        external_id = body.get("id")
        amount = body.get("amount")
        status = str(body.get("status") or "").strip().upper()
        currency = str(body.get("currency") or "").strip().upper()
        if not external_id or amount is None or not status:
            raise WebhookVerificationFailed("Missing required Platega webhook fields")
        if currency and currency != "RUB":
            raise WebhookVerificationFailed("Unsupported Platega webhook currency")

        try:
            payment_method = int(body.get("paymentMethod"))
        except (TypeError, ValueError):
            payment_method = None

        return WebhookResult(
            external_id=str(external_id).strip(),
            amount_rub=float(Decimal(str(amount))),
            provider_meta=json.dumps(body, default=str),
            should_fulfill=status == "CONFIRMED",
            provider_status=status,
            payment_method=payment_method,
        )

    @staticmethod
    def _normalize_amount(amount_rub: float) -> int | float:
        amount = Decimal(str(amount_rub)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if amount == amount.to_integral():
            return int(amount)
        return float(amount)
