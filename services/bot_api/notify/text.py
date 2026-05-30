from __future__ import annotations

from services.billing.schemas import OrderTypeEnum
from services.bot_api.notify.constants import NOTIFY_SUCCESS_EMOJI, NOTIFY_WALLET_EMOJI


def payment_completed_text(order_type: str) -> str:
    if order_type == OrderTypeEnum.TOP_UP.value:
        return f"{NOTIFY_SUCCESS_EMOJI} <b>Оплата подтверждена</b>"
    if order_type == OrderTypeEnum.DEVICE_SLOTS.value:
        return f"{NOTIFY_SUCCESS_EMOJI} <b>Оплата подтверждена</b>\n\nДополнительное устройство добавлено."
    if order_type == OrderTypeEnum.SUBSCRIPTION_RENEWAL.value:
        return f"{NOTIFY_SUCCESS_EMOJI} <b>Оплата подтверждена</b>\n\nПодписка продлена."
    return f"{NOTIFY_SUCCESS_EMOJI} <b>Оплата подтверждена</b>\n\nПодписка активирована."


def wallet_text(balance_rub: str) -> str:
    return f"{NOTIFY_WALLET_EMOJI} <b>Баланс: {balance_rub}</b>"
