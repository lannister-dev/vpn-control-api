from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from urllib import request
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.alerts.constants import DEDUP_WINDOW_SEC, AlertSource
from services.alerts.repository import AlertEventRepository
from services.alerts.schemas import (
    AlertEventOut,
    AlertLevel,
    AlertListOut,
    AlertMarkAllReadOut,
    AlertMessage,
    TelegramSendMessageIn,
)
from services.alerts.text import AlertTexts
from services.config import AlertsConfig, get_settings
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger


class AlertService:
    def __init__(self, session: AsyncSession, alerts_config: AlertsConfig | None = None):
        self.session = session
        self.repo = AlertEventRepository(session)
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

    async def record(
        self,
        *,
        level: AlertLevel,
        title: str,
        body: str,
        source: str = AlertSource.GENERIC,
        dedup_key: str | None = None,
        entity_id: str | None = None,
        send_telegram: bool = True,
    ) -> bool:
        telegram_ok = False
        if send_telegram:
            telegram_ok = await self.send(AlertMessage(level=level, title=title, body=body))

        existing = None
        if dedup_key:
            existing = await self.repo.find_active_by_dedup(
                source=source,
                dedup_key=dedup_key,
                within_seconds=DEDUP_WINDOW_SEC,
            )
        if existing is not None:
            await self.repo.bump_existing(existing, telegram_sent=telegram_ok)
        else:
            await self.repo.insert(
                level=level.value,
                source=source,
                title=title,
                body=body,
                dedup_key=dedup_key,
                entity_id=entity_id,
                telegram_sent=telegram_ok,
            )
        return telegram_ok

    async def resolve(self, *, source: str, dedup_key: str) -> int:
        return await self.repo.resolve_active(source=source, dedup_key=dedup_key)

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
        dedup_key = f"probe:{source}:node:{node_id}"
        if route_id is not None:
            dedup_key += f":route:{route_id}"
        if is_reachable:
            await self.resolve(source=AlertSource.PROBE, dedup_key=dedup_key)
            return await self.send(
                AlertMessage(
                    level=level,
                    title=AlertTexts.PROBE_STATUS_TITLE,
                    body=body,
                )
            )
        return await self.record(
            level=level,
            title=AlertTexts.PROBE_STATUS_TITLE,
            body=body,
            source=AlertSource.PROBE,
            dedup_key=dedup_key,
            entity_id=str(node_id),
        )

    async def list_for_admin(
        self,
        *,
        unread_only: bool,
        active_only: bool,
        level: AlertLevel | None,
        source: str | None,
        limit: int,
        offset: int,
    ) -> AlertListOut:
        rows, total = await self.repo.list_paginated(
            unread_only=unread_only,
            active_only=active_only,
            level=level.value if level else None,
            source=source,
            limit=limit,
            offset=offset,
        )
        unread = await self.repo.count_unread()
        return AlertListOut(
            items=[AlertEventOut.model_validate(r) for r in rows],
            total=total,
            unread=unread,
            limit=limit,
            offset=offset,
        )

    async def count_unread(self) -> int:
        return await self.repo.count_unread()

    async def mark_read(self, alert_id: UUID) -> AlertEventOut | None:
        await self.repo.mark_read(alert_id)
        row = await self.repo.get_by_id(alert_id)
        return AlertEventOut.model_validate(row) if row else None

    async def mark_all_read(self) -> AlertMarkAllReadOut:
        return AlertMarkAllReadOut(marked=await self.repo.mark_all_read())

    async def dismiss(self, alert_id: UUID) -> AlertEventOut | None:
        await self.repo.dismiss(alert_id)
        row = await self.repo.get_by_id(alert_id)
        return AlertEventOut.model_validate(row) if row else None

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


def get_alert_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> AlertService:
    return AlertService(session)
