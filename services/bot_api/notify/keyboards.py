from __future__ import annotations

from services.billing.schemas import OrderTypeEnum
from services.bot_api.notify.schemas import InlineKeyboardButton, InlineKeyboardMarkup


def payment_completed_keyboard(order_type: str) -> InlineKeyboardMarkup:
    if order_type == OrderTypeEnum.DEVICE_SLOTS.value:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📱 Устройства", callback_data="devices:open::"),
                    InlineKeyboardButton(text="🏠 Меню", callback_data="start:main_menu::"),
                ],
            ],
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 VPN", callback_data="connect:open::")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="start:main_menu::")],
        ],
    )


def wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="wallet:top_up::")],
            [
                InlineKeyboardButton(text="📋 История", callback_data="payment:history::"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="start:main_menu::"),
            ],
        ],
    )
