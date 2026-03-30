from __future__ import annotations

import asyncio
import json
import logging
from urllib import request

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
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await asyncio.to_thread(self._post_telegram_message, token, payload)

    async def send_payment_completed(self, *, chat_id: int, order_type: str) -> bool:
        return await self.send_message(
            chat_id=chat_id,
            text=self._payment_completed_text(order_type),
        )

    @staticmethod
    def _payment_completed_text(order_type: str) -> str:
        if order_type == "device_slots":
            return "✅ Оплата подтверждена. Дополнительное устройство добавлено."
        if order_type == "subscription_renewal":
            return "✅ Оплата подтверждена. Подписка продлена."
        return "✅ Оплата подтверждена. Подписка активирована."

    @staticmethod
    def _post_telegram_message(token: str, payload: dict) -> bool:
        req = request.Request(
            url=f"https://api.telegram.org/bot{token}/sendMessage",
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
        except Exception:
            log.exception("bot_notify_request_failed")
            return False


def get_telegram_bot_notify_service() -> TelegramBotNotifyService:
    return TelegramBotNotifyService()
