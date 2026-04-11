from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from services.billing.schemas import PaymentProviderEnum
from services.billing.utils import is_payment_provider_available

PAYMENT_PROVIDER_PRIORITY: tuple[PaymentProviderEnum, ...] = (
    PaymentProviderEnum.FREEKASSA,
    PaymentProviderEnum.PLATEGA,
    PaymentProviderEnum.CRYPTO,
)


def build_available_payment_providers(
    *,
    user_balance: Decimal,
    plan_price_rub: Decimal,
    plan_price_stars: int | None,
    billing_settings: object,
) -> list[PaymentProviderEnum]:
    providers = [
        provider
        for provider in PAYMENT_PROVIDER_PRIORITY
        if is_payment_provider_available(provider, billing_settings)
    ]
    if user_balance >= plan_price_rub:
        providers.append(PaymentProviderEnum.BALANCE)
    if plan_price_stars:
        providers.append(PaymentProviderEnum.STARS)
    return providers


def top_up_amount_stars(amount_rub: Decimal, rate: Decimal) -> int:
    return int((amount_rub / rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_plan_order_amount_stars(
    plan: Any,
    *,
    extra_devices: int = 0,
) -> int | None:
    raw_total = getattr(plan, "price_stars", None)
    total = int(raw_total) if raw_total is not None else None
    if total is None:
        return None

    raw_device_price_stars = getattr(plan, "device_price_stars", None)
    device_price_stars = (
        int(raw_device_price_stars)
        if raw_device_price_stars is not None
        else None
    )
    if extra_devices > 0 and device_price_stars:
        total += device_price_stars * extra_devices
    return total


def get_device_display_name(user_agent: str | None, index: int) -> str:
    if isinstance(user_agent, str):
        normalized = user_agent.strip()
        if normalized:
            return normalized[:80]
    return f"Устройство {index}"


def parse_happ_crypto_response(response: httpx.Response) -> str:
    text = response.text.strip()
    if not text:
        raise ValueError("Happ crypto API returned empty body")

    value = text
    content_type = response.headers.get("content-type", "").lower()
    if "application/json" in content_type or text[:1] in {"{", "["}:
        try:
            value = extract_happ_crypto_url(response.json())
        except Exception:
            value = text

    value = value.strip()
    if not value.startswith("happ://crypt5/"):
        raise ValueError(f"Unexpected Happ crypto payload: {value[:64]}")
    return value


def extract_happ_crypto_url(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in (
            "url",
            "encrypted_link",
            "encryptedLink",
            "encrypted_url",
            "encryptedUrl",
            "result",
            "data",
            "link",
        ):
            value = payload.get(key)
            if value:
                return extract_happ_crypto_url(value)
    if isinstance(payload, list):
        for item in payload:
            value = extract_happ_crypto_url(item)
            if value:
                return value
    raise ValueError("Unable to extract Happ crypto URL")
