from __future__ import annotations

from pydantic import BaseModel

from services.bot_api.notify.constants import TELEGRAM_PARSE_MODE_HTML


class InlineKeyboardButton(BaseModel):
    text: str
    callback_data: str | None = None
    url: str | None = None


class InlineKeyboardMarkup(BaseModel):
    inline_keyboard: list[list[InlineKeyboardButton]]


class SendMessagePayload(BaseModel):
    chat_id: str
    text: str
    parse_mode: str = TELEGRAM_PARSE_MODE_HTML
    disable_web_page_preview: bool = True
    reply_markup: InlineKeyboardMarkup | None = None


class EditMessageTextPayload(BaseModel):
    chat_id: str
    message_id: int
    text: str
    parse_mode: str = TELEGRAM_PARSE_MODE_HTML
    disable_web_page_preview: bool = True
    reply_markup: InlineKeyboardMarkup | None = None


class EditMessageCaptionPayload(BaseModel):
    chat_id: str
    message_id: int
    caption: str
    parse_mode: str = TELEGRAM_PARSE_MODE_HTML
    reply_markup: InlineKeyboardMarkup | None = None
