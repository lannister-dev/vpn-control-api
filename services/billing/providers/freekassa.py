from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import Request

from services.billing.exceptions import ProviderError, WebhookVerificationFailed
from services.billing.providers.base import (
    PaymentProvider,
    ProviderCreateResult,
    WebhookResult,
)
from services.config import get_settings


class FreeKassaProvider(PaymentProvider):
    def __init__(self) -> None:
        cfg = get_settings().billing
        self.api_url = (cfg.freekassa_api_url or "https://pay.fk.money/").strip()
        self.shop_id = (cfg.freekassa_shop_id or "").strip()
        self.secret_word_1 = cfg.freekassa_secret_word_1 or ""
        self.secret_word_2 = cfg.freekassa_secret_word_2 or ""
        self.currency = (cfg.freekassa_currency or "RUB").strip() or "RUB"

        if not self.shop_id:
            raise ProviderError("FreeKassa shop_id not configured")
        if not self.secret_word_1:
            raise ProviderError("FreeKassa secret word 1 not configured")

    async def create_payment(
        self,
        *,
        order_id: str,
        amount_rub: float,
        description: str,
        payment_method: int | None = None,
    ) -> ProviderCreateResult:
        external_id = f"fk_{uuid4().hex}"
        amount = self._format_amount(amount_rub)
        sign = self._sign_create(
            shop_id=self.shop_id,
            amount=amount,
            secret_word_1=self.secret_word_1,
            currency=self.currency,
            order_id=external_id,
        )
        query = {
            "m": self.shop_id,
            "oa": amount,
            "currency": self.currency,
            "o": external_id,
            "s": sign,
            "us_order_id": order_id,
            "us_description": description,
        }
        base_url = self.api_url if self.api_url.endswith("/") else f"{self.api_url}/"
        payment_url = f"{base_url}?{urlencode(query)}"
        return ProviderCreateResult(
            external_id=external_id,
            payment_url=payment_url,
            provider_meta=json.dumps(
                {
                    "merchant_id": self.shop_id,
                    "merchant_order_id": external_id,
                    "amount": amount,
                    "currency": self.currency,
                    "user_order_id": order_id,
                }
            ),
        )

    async def verify_webhook(self, request: Request) -> WebhookResult:
        params = await self._request_payload(request)

        merchant_id = self._pick(params, "MERCHANT_ID", "merchant_id", "m")
        amount = self._pick(params, "AMOUNT", "amount", "oa")
        order_id = self._pick(
            params,
            "MERCHANT_ORDER_ID",
            "merchant_order_id",
            "o",
        )
        signature = self._pick(params, "SIGN", "sign", "s")

        if not merchant_id or not amount or not order_id or not signature:
            raise WebhookVerificationFailed("Missing required FreeKassa webhook fields")
        if str(merchant_id).strip() != self.shop_id:
            raise WebhookVerificationFailed("FreeKassa merchant_id mismatch")
        if not self.secret_word_2:
            raise WebhookVerificationFailed("FreeKassa secret word 2 not configured")

        expected = self._sign_webhook(
            merchant_id=str(merchant_id).strip(),
            amount=str(amount).strip(),
            secret_word_2=self.secret_word_2,
            order_id=str(order_id).strip(),
        )
        if expected.lower() != str(signature).strip().lower():
            raise WebhookVerificationFailed("Invalid FreeKassa signature")

        try:
            amount_rub = float(Decimal(str(amount).strip()))
        except Exception as exc:
            raise WebhookVerificationFailed("Invalid FreeKassa amount") from exc

        return WebhookResult(
            external_id=str(order_id).strip(),
            amount_rub=amount_rub,
            provider_meta=json.dumps(params, default=str),
        )

    @staticmethod
    def _pick(data: dict[str, object], *keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return None

    @staticmethod
    async def _request_payload(request: Request) -> dict[str, object]:
        if request.method.upper() == "GET":
            return dict(request.query_params)

        content_type = request.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            body = await request.json()
            if isinstance(body, dict):
                return body
            raise WebhookVerificationFailed("Invalid FreeKassa JSON payload")

        form = await request.form()
        return dict(form)

    @staticmethod
    def _format_amount(amount_rub: float) -> str:
        amount = Decimal(str(amount_rub)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        text = format(amount, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    @staticmethod
    def _md5(value: str) -> str:
        return hashlib.md5(value.encode("utf-8")).hexdigest()

    @classmethod
    def _sign_create(
        cls,
        *,
        shop_id: str,
        amount: str,
        secret_word_1: str,
        currency: str,
        order_id: str,
    ) -> str:
        return cls._md5(f"{shop_id}:{amount}:{secret_word_1}:{currency}:{order_id}")

    @classmethod
    def _sign_webhook(
        cls,
        *,
        merchant_id: str,
        amount: str,
        secret_word_2: str,
        order_id: str,
    ) -> str:
        return cls._md5(f"{merchant_id}:{amount}:{secret_word_2}:{order_id}")
