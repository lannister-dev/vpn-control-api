from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

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


def get_device_display_name(
    user_agent: str | None,
    index: int,
    *,
    device_model: str | None = None,
    platform: str | None = None,
    os_version: str | None = None,
) -> str:
    if isinstance(device_model, str):
        model = device_model.strip()
        if model:
            return _enrich_with_os(model, platform, os_version)
    if isinstance(platform, str):
        plat = platform.strip()
        if plat:
            return _enrich_with_os(plat.capitalize(), None, os_version)
    if isinstance(user_agent, str):
        normalized = user_agent.strip()
        if normalized:
            return normalized[:80]
    return f"Устройство {index}"


def _enrich_with_os(label: str, platform: str | None, os_version: str | None) -> str:
    parts = [label]
    if platform and platform.strip().lower() not in label.lower():
        parts.append(platform.strip())
    if os_version and os_version.strip():
        parts.append(os_version.strip())
    return " · ".join(parts)[:80]
