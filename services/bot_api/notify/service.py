from __future__ import annotations

import logging

from pydantic import BaseModel

from services.billing.schemas import OrderTypeEnum
from services.bot_api.notify.constants import TELEGRAM_API_BASE, TELEGRAM_HTTP_TIMEOUT_SEC
from services.bot_api.notify.keyboards import payment_completed_keyboard, wallet_keyboard
from services.bot_api.notify.schemas import (
    EditMessageCaptionPayload,
    EditMessageTextPayload,
    InlineKeyboardMarkup,
    SendMessagePayload,
)
from services.bot_api.notify.text import payment_completed_text, wallet_text
from services.config import BotNotificationsConfig, get_settings
from shared.api.base_client import BaseApiClient, HttpError
from shared.utils.logger import StructuredLogger

log = StructuredLogger(logging.getLogger("bot-notify"))


class TelegramBotNotifyService:
    def __init__(self, config: BotNotificationsConfig | None = None):
        self.config = config or get_settings().bot_notifications
        self._client = BaseApiClient(
            base_url=TELEGRAM_API_BASE,
            headers={},
            timeout_s=float(TELEGRAM_HTTP_TIMEOUT_SEC),
        )

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        token = self._resolve_token(chat_id)
        if not token:
            return False
        payload = SendMessagePayload(
            chat_id=str(chat_id),
            text=text,
            reply_markup=reply_markup,
        )
        return await self._call("sendMessage", token=token, payload=payload)

    async def send_payment_completed(
        self,
        *,
        chat_id: int,
        order_type: str,
        pending_message: tuple[int, int] | None = None,
    ) -> bool:
        text = payment_completed_text(order_type)
        if order_type == OrderTypeEnum.TOP_UP.value:
            return await self.send_message(chat_id=chat_id, text=text)
        markup = payment_completed_keyboard(order_type)
        if pending_message:
            edited = await self.edit_message(
                chat_id=pending_message[0],
                message_id=pending_message[1],
                text=text,
                reply_markup=markup,
            )
            if edited:
                return True
        return await self.send_message(chat_id=chat_id, text=text, reply_markup=markup)

    async def replace_pending_with_wallet(
        self,
        *,
        balance_rub: str,
        pending_message: tuple[int, int] | None,
    ) -> bool:
        if not pending_message:
            return False
        return await self.edit_message(
            chat_id=pending_message[0],
            message_id=pending_message[1],
            text=wallet_text(balance_rub),
            reply_markup=wallet_keyboard(),
        )

    async def edit_message(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        token = self._resolve_token(chat_id)
        if not token:
            return False
        text_payload = EditMessageTextPayload(
            chat_id=str(chat_id),
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        if await self._call("editMessageText", token=token, payload=text_payload):
            return True
        caption_payload = EditMessageCaptionPayload(
            chat_id=str(chat_id),
            message_id=message_id,
            caption=text,
            reply_markup=reply_markup,
        )
        return await self._call("editMessageCaption", token=token, payload=caption_payload)

    def _resolve_token(self, chat_id: int) -> str | None:
        if not self.config.enabled:
            return None
        token = (self.config.bot_token or "").strip()
        if not token:
            log.info("bot_notify_skipped_no_token", chat_id=str(chat_id))
            return None
        return token

    async def _call(self, method: str, *, token: str, payload: BaseModel) -> bool:
        body = payload.model_dump(mode="json", exclude_none=True)
        try:
            response = await self._client.post(f"/bot{token}/{method}", json=body)
        except HttpError as e:
            log.warning(
                "bot_notify_http_error",
                method=method,
                http_status=e.status,
                body=e.body,
            )
            return False
        except Exception:
            log.exception("bot_notify_request_failed", method=method)
            return False
        if isinstance(response, dict) and response.get("ok") is False:
            log.warning("bot_notify_rejected", response=response)
            return False
        return True


def get_telegram_bot_notify_service() -> TelegramBotNotifyService:
    return TelegramBotNotifyService()
