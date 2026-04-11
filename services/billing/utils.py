from __future__ import annotations

from enum import Enum


def _provider_value(provider: str | Enum) -> str:
    if isinstance(provider, Enum):
        return str(provider.value)
    return str(provider)


def validate_provider_payment_method(
    provider: str | Enum,
    *,
    payment_method: int | None = None,
) -> None:
    provider_value = _provider_value(provider)
    if provider_value == "platega" and payment_method is None:
        raise ValueError(f"payment_method is required for provider='{provider_value}'")


def is_payment_provider_available(provider: str | Enum, billing: object) -> bool:
    provider_value = _provider_value(provider)
    if provider_value == "freekassa":
        return bool(
            str(getattr(billing, "freekassa_shop_id", "")).strip()
            and getattr(billing, "freekassa_secret_word_1", "")
            and getattr(billing, "freekassa_secret_word_2", "")
        )
    if provider_value == "crypto":
        return bool(
            getattr(billing, "crypto_api_key", "")
            and getattr(billing, "crypto_shop_id", "")
        )
    if provider_value == "platega":
        return bool(
            getattr(billing, "platega_api_url", "")
            and getattr(billing, "platega_shop_id", "")
            and getattr(billing, "platega_api_key", "")
        )
    if provider_value == "stars":
        return bool(getattr(billing, "stars_bot_token", ""))
    if provider_value == "balance":
        return True
    return False
