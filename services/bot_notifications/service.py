from __future__ import annotations

import asyncio
import json
import logging
from urllib import request
from urllib.error import HTTPError

from services.config import BotNotificationsConfig, get_settings
from shared.utils.logger import StructuredLogger

log = StructuredLogger(logging.getLogger("bot-notify"))


class TelegramBotNotifyService:
    def __init__(self, config: BotNotificationsConfig | None = None):
        self.config = config or get_settings().bot_notifications

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> bool:
        if not self.config.enabled:
            return False
        token = (self.config.bot_token or "").strip()
        if not token:
            log.info("bot_notify_skipped_no_token", chat_id=str(chat_id))
            return False

        payload: dict[str, object] = {
            "chat_id": str(chat_id),
            "text": text,
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await asyncio.to_thread(
            self._post_telegram_request,
            token,
            "sendMessage",
            payload,
        )

    async def send_payment_completed(
        self,
        *,
        chat_id: int,
        order_type: str,
        pending_message: tuple[int, int] | None = None,
    ) -> bool:
        if order_type == "top_up":
            return await self.send_message(
                chat_id=chat_id,
                text=self._payment_completed_text(order_type),
            )
        text = self._payment_completed_text(order_type)
        reply_markup = self._payment_completed_markup(order_type)
        if pending_message:
            edited = await self.edit_message(
                chat_id=pending_message[0],
                message_id=pending_message[1],
                text=text,
                reply_markup=reply_markup,
            )
            if edited:
                return True
        return await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )

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
            text=self._wallet_text(balance_rub),
            reply_markup=self._wallet_markup(),
        )

    _SUCCESS_EMOJI = '<tg-emoji emoji-id="5118392447394644756">✅</tg-emoji>'

    @staticmethod
    def _payment_completed_text(order_type: str) -> str:
        ok = TelegramBotNotifyService._SUCCESS_EMOJI
        if order_type == "top_up":
            return f"{ok} <b>Оплата подтверждена</b>"
        if order_type == "device_slots":
            return f"{ok} <b>Оплата подтверждена</b>\n\nДополнительное устройство добавлено."
        if order_type == "subscription_renewal":
            return f"{ok} <b>Оплата подтверждена</b>\n\nПодписка продлена."
        return f"{ok} <b>Оплата подтверждена</b>\n\nПодписка активирована."

    @staticmethod
    def _payment_completed_markup(order_type: str) -> dict[str, object]:
        if order_type == "device_slots":
            buttons = [
                [
                    {"text": "📱 Устройства", "callback_data": "devices:open::"},
                    {"text": "🏠 Меню", "callback_data": "start:main_menu::"},
                ]
            ]
        else:
            buttons = [
                [{"text": "🚀 VPN", "callback_data": "connect:open::"}],
                [{"text": "🏠 Меню", "callback_data": "start:main_menu::"}],
            ]
        return {"inline_keyboard": buttons}

    @staticmethod
    def _wallet_text(balance_rub: str) -> str:
        return f"💰 <b>Баланс: {balance_rub}</b>"

    @staticmethod
    def _wallet_markup() -> dict[str, object]:
        return {
            "inline_keyboard": [
                [{"text": "💳 Пополнить", "callback_data": "wallet:top_up::"}],
                [
                    {"text": "📋 История", "callback_data": "payment:history::"},
                    {"text": "🏠 Меню", "callback_data": "start:main_menu::"},
                ],
            ]
        }

    async def edit_message(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> bool:
        if not self.config.enabled:
            return False
        token = (self.config.bot_token or "").strip()
        if not token:
            log.info("bot_notify_skipped_no_token", chat_id=str(chat_id))
            return False

        payload: dict[str, object] = {
            "chat_id": str(chat_id),
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        edited = await asyncio.to_thread(
            self._post_telegram_request,
            token,
            "editMessageText",
            payload,
        )
        if edited:
            return True
        caption_payload = {
            "chat_id": str(chat_id),
            "message_id": message_id,
            "caption": text,
            "parse_mode": "HTML",
        }
        if reply_markup:
            caption_payload["reply_markup"] = reply_markup
        return await asyncio.to_thread(
            self._post_telegram_request,
            token,
            "editMessageCaption",
            caption_payload,
        )

    @staticmethod
    def _post_telegram_request(token: str, method: str, payload: dict) -> bool:
        req = request.Request(
            url=f"https://api.telegram.org/bot{token}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                body = response.read().decode("utf-8")
                if response.status >= 400:
                    log.warning("bot_notify_failed", http_status=response.status, body=body)
                    return False
                data = json.loads(body) if body else {}
                if isinstance(data, dict) and data.get("ok") is False:
                    log.warning("bot_notify_rejected", response=data)
                    return False
                return True
        except HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            log.warning(
                "bot_notify_http_error",
                method=method,
                http_status=e.code,
                body=error_body,
            )
            return False
        except Exception:
            log.exception("bot_notify_request_failed")
            return False


def get_telegram_bot_notify_service() -> TelegramBotNotifyService:
    return TelegramBotNotifyService()
