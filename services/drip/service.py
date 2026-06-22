from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.config import get_settings
from services.drip.constants import DripCondition, DripStatus
from services.drip.models import DripStep, UserCampaignState
from services.drip.repository import DripRepository
from services.support.constants import BROADCAST_BUTTON_STYLES
from services.support.schemas import (
    SupportOutboundAttachmentMsg,
    SupportOutboundInlineButton,
    SupportOutboundPayload,
)
from services.support.service import SupportService
from services.users.repository import UserRepository
from shared.nats.client import NatsClient
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("drip-service"))


class DripService:
    def __init__(
        self, session, *, nats_client: NatsClient | None, outbound_subject: str
    ):
        self.session = session
        self._nats = nats_client
        self._outbound_subject = outbound_subject
        self.repo = DripRepository(session)
        self.users = UserRepository(session)

    async def enroll_for_event(self, *, event_kind: str, telegram_id: int) -> int:
        campaigns = await self.repo.active_campaigns_by_trigger(event_kind)
        if not campaigns:
            return 0
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return 0
        now = datetime.now(timezone.utc)
        enrolled = 0
        for campaign in campaigns:
            steps = sorted(campaign.steps, key=lambda s: s.step_order)
            if not steps:
                continue
            first_at = now + timedelta(seconds=int(steps[0].delay_seconds))
            if await self.repo.enroll(
                user_id=user.id,
                campaign_id=campaign.id,
                entered_at=now,
                next_send_at=first_at,
            ):
                enrolled += 1
        return enrolled

    async def run_due(self, *, now: datetime, limit: int) -> int:
        states = await self.repo.list_due(now=now, limit=limit)
        sent = 0
        for state in states:
            if await self._process_state(state, now=now):
                sent += 1
        return sent

    async def _process_state(self, state: UserCampaignState, *, now: datetime) -> bool:
        campaign = await self.repo.get_campaign_with_steps(state.campaign_id)
        if campaign is None or not campaign.is_active:
            state.status = DripStatus.STOPPED
            return False
        steps = sorted(campaign.steps, key=lambda s: s.step_order)
        user = await self.users.get_by_id(state.user_id)
        if user is None:
            state.status = DripStatus.ABANDONED
            return False
        if getattr(user, "suppress_marketing", False):
            state.status = DripStatus.STOPPED
            return False
        if state.current_step >= len(steps):
            state.status = DripStatus.COMPLETED
            state.next_send_at = None
            return False
        step = steps[state.current_step]
        if not await self._condition_holds(step.condition, state.user_id):
            state.status = DripStatus.COMPLETED
            state.next_send_at = None
            return False

        ok = await self._send_step(state, step, telegram_id=int(user.telegram_id))
        state.last_step_sent_at = now
        next_index = state.current_step + 1
        state.current_step = next_index
        if next_index >= len(steps):
            state.status = DripStatus.COMPLETED
            state.next_send_at = None
        else:
            state.next_send_at = now + timedelta(
                seconds=int(steps[next_index].delay_seconds)
            )
        return ok

    async def _condition_holds(self, condition: str, user_id: UUID) -> bool:
        if condition == DripCondition.NOT_CONNECTED:
            return not await self.repo.has_connected(user_id)
        if condition == DripCondition.NOT_PURCHASED:
            return not await self.repo.has_paid(user_id)
        return True

    async def _send_step(
        self, state: UserCampaignState, step: DripStep, *, telegram_id: int
    ) -> bool:
        if self._nats is None:
            return False
        await self._ensure_outbound_stream()
        media: list[SupportOutboundAttachmentMsg] = []
        if step.media_url and step.media_kind:
            media.append(
                SupportOutboundAttachmentMsg(kind=step.media_kind, url=step.media_url)
            )
        buttons: list[SupportOutboundInlineButton] = []
        for b in step.inline_buttons or []:
            text = (b.get("text") or "").strip()
            url = (b.get("url") or "").strip()
            if text and SupportService._is_valid_button_url(url):
                style = b.get("style")
                style = style if style in BROADCAST_BUTTON_STYLES else None
                buttons.append(SupportOutboundInlineButton(text=text, url=url, style=style))
        payload = SupportOutboundPayload(
            ticket_id=f"drip:{state.campaign_id}",
            message_id=f"drip:{state.id}:{state.current_step}",
            telegram_id=telegram_id,
            text=step.text_body,
            media=media,
            buttons=buttons,
            entities=None,
            parse_mode="HTML",
            kind="broadcast",
        )
        try:
            await self._nats.publish_jetstream(
                subject=self._outbound_subject,
                payload=payload.model_dump(),
                msg_id=payload.message_id,
            )
            return True
        except Exception:
            logger.exception(
                "drip_publish_failed",
                state_id=str(state.id),
                step=state.current_step,
            )
            return False

    async def _ensure_outbound_stream(self) -> None:
        if self._nats is None:
            return
        try:
            s = get_settings().nats
            await self._nats.ensure_stream(
                name=s.js_support_stream,
                subjects=[
                    s.support_inbound_subject,
                    s.support_outbound_subject,
                    s.support_sent_subject,
                ],
                max_msgs_per_subject=s.js_support_max_msgs_per_subject,
                max_age=s.js_support_max_age_s,
                duplicate_window=s.js_support_duplicate_window_s,
            )
        except Exception:
            logger.warning("drip_ensure_stream_failed")
