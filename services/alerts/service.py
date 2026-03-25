from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from urllib import request
from uuid import UUID

from services.alerts.schemas import AlertLevel, AlertMessage, TelegramSendMessageIn
from services.alerts.text import AlertTexts
from services.config import AlertsConfig, get_settings
from shared.utils.logger import StructuredLogger


class AlertService:
    def __init__(self, alerts_config: AlertsConfig | None = None):
        self.alerts_config = alerts_config or get_settings().alerts
        self.logger = StructuredLogger(logging.getLogger("alert-service"))

    async def send(self, payload: AlertMessage) -> bool:
        if not self.alerts_config.telegram_enabled:
            return False
        if not self.alerts_config.telegram_bot_token or not self.alerts_config.telegram_chat_id:
            self.logger.warning("telegram alerts are enabled but bot token/chat id is not configured")
            return False

        emoji = self._level_emoji(payload.level)
        telegram_message = TelegramSendMessageIn(
            chat_id=self.alerts_config.telegram_chat_id,
            text=AlertTexts.TELEGRAM_MESSAGE.format(
                level_prefix=emoji,
                title=payload.title,
                body=payload.body,
            ),
        )
        return await asyncio.to_thread(self._post_telegram, telegram_message)

    async def send_probe_status_change(
            self,
            *,
            node_id: UUID,
            node_name: str,
            region: str,
            source: str,
            is_reachable: bool,
            checked_at: datetime,
            error: str | None,
            route_id: UUID | None = None,
            transport_kind: str | None = None,
            probe_kind: str | None = None,
            target_host: str | None = None,
            target_port: int | None = None,
            error_phase: str | None = None,
    ) -> bool:
        state = "RECOVERED" if is_reachable else "FAILED"
        level = AlertLevel.info if is_reachable else AlertLevel.critical
        error_text = error or "-"
        target = "-"
        if target_host:
            target = f"{target_host}:{target_port}" if target_port is not None else target_host
        body = AlertTexts.PROBE_STATUS_BODY.format(
            node_name=node_name,
            node_id=node_id,
            region=region,
            source=source,
            route_id=str(route_id) if route_id is not None else "-",
            transport_kind=transport_kind or "-",
            probe_kind=probe_kind or "-",
            target=target,
            state=state,
            checked_at=checked_at.isoformat(),
            error_phase=error_phase or "-",
            error=error_text,
        )
        return await self.send(
            AlertMessage(
                level=level,
                title=AlertTexts.PROBE_STATUS_TITLE,
                body=body,
            )
        )

    def _post_telegram(self, payload: TelegramSendMessageIn) -> bool:
        url = f"https://api.telegram.org/bot{self.alerts_config.telegram_bot_token}/sendMessage"
        req = request.Request(
            url=url,
            data=json.dumps(payload.model_dump()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = max(1, int(self.alerts_config.telegram_timeout_sec))
        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                if response.status >= 400:
                    self.logger.warning(
                        "telegram alert failed",
                        http_status=response.status,
                        body=body,
                    )
                    return False
                parsed = json.loads(body) if body else {}
                if isinstance(parsed, dict) and parsed.get("ok") is False:
                    self.logger.warning("telegram alert rejected by API", response=parsed)
                    return False
                return True
        except Exception:
            self.logger.exception("telegram alert request failed")
            return False

    @staticmethod
    def _level_emoji(level: AlertLevel) -> str:
        if level == AlertLevel.critical:
            return "CRIT"
        if level == AlertLevel.warning:
            return "WARN"
        return "INFO"


def get_alert_service() -> AlertService:
    return AlertService()
