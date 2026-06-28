import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.scenarios.constants import (
    SCENARIO_BUTTON_ACTIONS,
    SCENARIO_BUTTON_STYLES,
    ScenarioCondition,
    ScenarioStatus,
)
from services.scenarios.models import (
    ScenarioCampaign,
    ScenarioEdge,
    ScenarioNode,
    ScenarioState,
)
from services.scenarios.repository import ScenarioRepository
from services.scenarios.schemas import (
    ScenarioCampaignIn,
    ScenarioCampaignListOut,
    ScenarioCampaignOut,
    ScenarioCampaignStat,
    ScenarioEdgeOut,
    ScenarioNodeOut,
    ScenarioStatsOut,
)
from services.support.constants import SUPPORT_OUTBOUND_SUBJECT
from services.support.schemas import (
    SupportOutboundAttachmentMsg,
    SupportOutboundInlineButton,
    SupportOutboundPayload,
)
from services.users.repository import UserRepository
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.utils.logger import StructuredLogger

logger_scenario = StructuredLogger(logging.getLogger("scenario-service"))


class ScenarioUserNotReady(Exception):
    """Trigger event matched active campaigns but the user row isn't visible yet
    (publish happened before the creating transaction committed). Signals a retry."""


class ScenarioService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        nats_client: NatsClient | None = None,
        outbound_subject: str = SUPPORT_OUTBOUND_SUBJECT,
    ):
        self.session = session
        self.scenarios = ScenarioRepository(session)
        self.users = UserRepository(session)
        self._nats = nats_client
        self._outbound_subject = outbound_subject

    @staticmethod
    def _nodes_by_key(campaign: ScenarioCampaign) -> dict[str, ScenarioNode]:
        return {n.node_key: n for n in campaign.nodes}

    @staticmethod
    def _next_edge_key(
        campaign: ScenarioCampaign, from_key: str, *, branch: str | None
    ) -> str | None:
        for e in campaign.edges:
            if e.from_key != from_key:
                continue
            if branch is None:
                if e.branch is None:
                    return e.to_key
            elif e.branch == branch:
                return e.to_key
        if branch is not None:
            for e in campaign.edges:
                if e.from_key == from_key:
                    return e.to_key
        return None

    async def enroll_for_event(self, *, event_kind: str, telegram_id: int) -> int:
        campaigns = await self.scenarios.active_campaigns_by_trigger(event_kind)
        if not campaigns:
            return 0
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise ScenarioUserNotReady(telegram_id)
        now = datetime.now(timezone.utc)
        enrolled = 0
        for campaign in campaigns:
            entry_key = campaign.entry_node_key
            if not entry_key:
                continue
            entry = self._nodes_by_key(campaign).get(entry_key)
            if entry is None:
                continue
            delay = int(entry.delay_seconds) if entry.node_type == "message" else 0
            if await self.scenarios.enroll(
                user_id=user.id,
                campaign_id=campaign.id,
                entered_at=now,
                next_send_at=now + timedelta(seconds=delay),
                current_node_key=entry_key,
            ):
                enrolled += 1
        return enrolled

    async def run_due(self, *, now: datetime, limit: int) -> int:
        states = await self.scenarios.list_due(now=now, limit=limit)
        sent = 0
        for state in states:
            if await self._process_state(state, now=now):
                sent += 1
        return sent

    async def _walk_to_waitpoint(
        self, state: ScenarioState, campaign: ScenarioCampaign,
        nodes: dict[str, ScenarioNode], *, start_key: str | None, now: datetime,
    ) -> None:
        """Route through condition nodes (no send) until a message wait-point or terminal."""
        key = start_key
        guard = 0
        while key is not None and guard < 64:
            guard += 1
            node = nodes.get(key)
            if node is None or node.node_type == "end":
                state.current_node_key = key
                state.status = ScenarioStatus.COMPLETED
                state.next_send_at = None
                return
            if node.node_type == "condition":
                holds = await self._condition_holds(
                    node.check_kind or "always", state.user_id
                )
                key = self._next_edge_key(campaign, key, branch="yes" if holds else "no")
                continue
            state.current_node_key = key
            state.node_sends = 0
            state.next_send_at = now + timedelta(seconds=int(node.delay_seconds))
            return
        state.status = ScenarioStatus.COMPLETED
        state.next_send_at = None

    async def _process_state(self, state: ScenarioState, *, now: datetime) -> bool:
        campaign = await self.scenarios.get_campaign_with_graph(state.campaign_id)
        if campaign is None or not campaign.is_active:
            state.status = ScenarioStatus.STOPPED
            return False
        user = await self.users.get_by_id(state.user_id)
        if user is None:
            state.status = ScenarioStatus.ABANDONED
            return False
        if getattr(user, "suppress_marketing", False):
            state.status = ScenarioStatus.STOPPED
            return False

        nodes = self._nodes_by_key(campaign)
        node = nodes.get(state.current_node_key)
        if node is None:
            state.status = ScenarioStatus.COMPLETED
            state.next_send_at = None
            return False

        if node.node_type == "condition":
            await self._walk_to_waitpoint(
                state, campaign, nodes, start_key=state.current_node_key, now=now
            )
            return False
        if node.node_type == "end":
            state.status = ScenarioStatus.COMPLETED
            state.next_send_at = None
            return False

        # message node — its delay has elapsed, send if the gate holds
        if not await self._condition_holds(node.condition, state.user_id):
            state.status = ScenarioStatus.COMPLETED
            state.next_send_at = None
            return False
        ok = await self._send_message(state, node, user=user)
        state.last_step_sent_at = now
        state.node_sends = int(state.node_sends or 0) + 1

        # repeat the same reminder until the cap is hit (gate above stops it early
        # the moment the user does the action — e.g. connects / takes the trial)
        repeat_cap = max(1, int(node.repeat_count or 1))
        if state.node_sends < repeat_cap:
            gap = int(node.repeat_interval_sec or 0) or int(node.delay_seconds or 0)
            state.next_send_at = now + timedelta(seconds=gap)
            return ok

        await self._walk_to_waitpoint(
            state, campaign, nodes,
            start_key=self._next_edge_key(campaign, node.node_key, branch=None),
            now=now,
        )
        return ok

    async def list_campaigns(self) -> ScenarioCampaignListOut:
        campaigns = await self.scenarios.list_campaigns()
        return ScenarioCampaignListOut(items=[self._campaign_to_out(c) for c in campaigns])

    @staticmethod
    def _campaign_to_out(campaign: ScenarioCampaign) -> ScenarioCampaignOut:
        nodes = [
            ScenarioNodeOut(
                id=n.id, key=n.node_key, type=n.node_type,
                pos_cx=n.pos_cx, pos_top=n.pos_top,
                delay_seconds=n.delay_seconds, condition=n.condition,
                repeat_count=n.repeat_count, repeat_interval_sec=n.repeat_interval_sec,
                text_body=n.text_body, inline_buttons=n.inline_buttons,
                media_kind=n.media_kind, media_url=n.media_url,
                check=n.check_kind, conversion=n.conversion, label=n.label,
            )
            for n in campaign.nodes
        ]
        edges = [
            ScenarioEdgeOut(id=e.id, from_node=e.from_key, to_node=e.to_key, branch=e.branch)
            for e in campaign.edges
        ]
        return ScenarioCampaignOut(
            id=campaign.id, key=campaign.key, name=campaign.name,
            trigger_event=campaign.trigger_event, is_active=campaign.is_active,
            entry_node_key=campaign.entry_node_key, nodes=nodes, edges=edges,
        )

    async def stats(self) -> ScenarioStatsOut:
        rows = await self.scenarios.status_counts()
        agg: dict[UUID, dict[str, int]] = {}
        for campaign_id, status, count in rows:
            bucket = agg.setdefault(
                campaign_id,
                {"active": 0, "completed": 0, "abandoned": 0, "stopped": 0},
            )
            if status in bucket:
                bucket[status] += count
        node_agg: dict[UUID, dict[str, int]] = {}
        for campaign_id, node_key, count in await self.scenarios.active_node_counts():
            node_agg.setdefault(campaign_id, {})[node_key] = count
        items = [
            ScenarioCampaignStat(
                campaign_id=campaign_id,
                enrolled=sum(bucket.values()),
                node_active=node_agg.get(campaign_id, {}),
                **bucket,
            )
            for campaign_id, bucket in agg.items()
        ]
        return ScenarioStatsOut(items=items)

    @staticmethod
    def _build_nodes(payload: ScenarioCampaignIn) -> list[ScenarioNode]:
        return [
            ScenarioNode(
                node_key=n.key, node_type=n.type,
                pos_cx=n.pos_cx, pos_top=n.pos_top,
                delay_seconds=n.delay_seconds, condition=n.condition,
                repeat_count=n.repeat_count, repeat_interval_sec=n.repeat_interval_sec,
                text_body=n.text_body, inline_buttons=n.inline_buttons,
                media_kind=n.media_kind, media_url=n.media_url,
                check_kind=n.check, conversion=n.conversion, label=n.label,
            )
            for n in payload.nodes
        ]

    @staticmethod
    def _build_edges(payload: ScenarioCampaignIn) -> list[ScenarioEdge]:
        return [
            ScenarioEdge(from_key=e.from_node, to_key=e.to_node, branch=e.branch)
            for e in payload.edges
        ]

    @staticmethod
    def _resolve_entry_key(payload: ScenarioCampaignIn) -> str | None:
        if payload.entry_node_key:
            return payload.entry_node_key
        targets = {e.to_node for e in payload.edges}
        for n in payload.nodes:
            if n.type != "end" and n.key not in targets:
                return n.key
        for n in payload.nodes:
            if n.type == "message":
                return n.key
        return None

    async def create_campaign(self, payload: ScenarioCampaignIn) -> ScenarioCampaignOut:
        campaign = ScenarioCampaign(
            key=payload.key,
            name=payload.name,
            trigger_event=payload.trigger_event,
            is_active=payload.is_active,
            entry_node_key=self._resolve_entry_key(payload),
        )
        campaign.nodes = self._build_nodes(payload)
        campaign.edges = self._build_edges(payload)
        self.session.add(campaign)
        await self.session.commit()
        return self._campaign_to_out(campaign)

    async def update_campaign(
        self, campaign_id: UUID, payload: ScenarioCampaignIn
    ) -> ScenarioCampaignOut | None:
        campaign = await self.scenarios.get_campaign_with_graph(campaign_id)
        if campaign is None:
            return None
        campaign.key = payload.key
        campaign.name = payload.name
        campaign.trigger_event = payload.trigger_event
        campaign.is_active = payload.is_active
        campaign.entry_node_key = self._resolve_entry_key(payload)
        campaign.nodes.clear()
        campaign.edges.clear()
        await self.session.flush()
        for node in self._build_nodes(payload):
            campaign.nodes.append(node)
        for edge in self._build_edges(payload):
            campaign.edges.append(edge)
        await self.session.commit()
        return self._campaign_to_out(campaign)

    async def set_active(
        self, campaign_id: UUID, is_active: bool
    ) -> ScenarioCampaignOut | None:
        campaign = await self.scenarios.get_campaign_with_graph(campaign_id)
        if campaign is None:
            return None
        campaign.is_active = is_active
        await self.session.commit()
        return self._campaign_to_out(campaign)

    async def delete_campaign(self, campaign_id: UUID) -> bool:
        campaign = await self.scenarios.get_campaign_with_graph(campaign_id)
        if campaign is None:
            return False
        await self.session.delete(campaign)
        await self.session.commit()
        return True

    async def _condition_holds(self, condition: str, user_id: UUID) -> bool:
        if condition == ScenarioCondition.NOT_CONNECTED:
            return not await self.scenarios.has_connected(user_id)
        if condition == ScenarioCondition.NOT_PURCHASED:
            return not await self.scenarios.has_paid(user_id)
        if condition == ScenarioCondition.NO_ACTIVE_SUB:
            return not await self.scenarios.has_active_subscription(
                user_id, now=datetime.now(timezone.utc)
            )
        if condition == ScenarioCondition.CONNECTED:
            return await self.scenarios.has_connected(user_id)
        if condition == ScenarioCondition.PURCHASED:
            return await self.scenarios.has_paid(user_id)
        return True

    @staticmethod
    def _render_text(text: str, user) -> str:
        if not text:
            return text
        out = text
        if "{name}" in out:
            username = (getattr(user, "username", None) or "").strip()
            if username:
                out = out.replace("{name}", username)
            else:
                out = re.sub(
                    r"[ \t]*,[ \t]*\{name\}|\{name\}[ \t]*,[ \t]*|[ \t]*\{name\}", "", out
                )
        if "{referral}" in out:
            bot_username = (get_settings().referral.bot_username or "").strip()
            code = getattr(user, "referral_code", None)
            link = (
                f"https://t.me/{bot_username}?start=ref_{code}"
                if bot_username and code
                else ""
            )
            out = out.replace("{referral}", link)
        return out

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
            logger_scenario.warning("scenario_ensure_stream_failed")

    @staticmethod
    def _build_outbound_button(b: dict) -> SupportOutboundInlineButton | None:
        text = (b.get("text") or "").strip()
        if not text:
            return None
        style = b.get("style")
        style = style if style in SCENARIO_BUTTON_STYLES else None
        action = b.get("action")
        if action == "promo":
            code = (b.get("value") or "").strip()
            if not code:
                return None
            return SupportOutboundInlineButton(text=text, action="promo", value=code, style=style)
        if action in SCENARIO_BUTTON_ACTIONS:
            return SupportOutboundInlineButton(text=text, action=action, style=style)
        url = (b.get("url") or "").strip()
        if ScenarioService._is_valid_button_url(url):
            return SupportOutboundInlineButton(text=text, url=url, style=style)
        return None

    @staticmethod
    def _is_valid_button_url(url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme in ("http", "https"):
            return bool(parsed.netloc)
        if parsed.scheme == "tg":
            return bool(parsed.netloc or parsed.path)
        return False

    async def _send_message(self, state: ScenarioState, node: ScenarioNode, *, user) -> bool:
        if self._nats is None:
            return False
        telegram_id = int(user.telegram_id)
        await self._ensure_outbound_stream()
        media: list[SupportOutboundAttachmentMsg] = []
        if node.media_url and node.media_kind:
            media.append(SupportOutboundAttachmentMsg(kind=node.media_kind, url=node.media_url))
        buttons: list[SupportOutboundInlineButton] = []
        for b in node.inline_buttons or []:
            btn = self._build_outbound_button(b)
            if btn is not None:
                buttons.append(btn)
        payload = SupportOutboundPayload(
            ticket_id=f"scenario:{state.campaign_id}",
            message_id=f"scenario:{state.id}:{node.node_key}:{state.node_sends or 0}",
            telegram_id=telegram_id,
            text=self._render_text(node.text_body or "", user),
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
            logger_scenario.exception(
                "scenario_publish_failed",
                state_id=str(state.id),
                node=node.node_key,
            )
            return False


def get_scenario_service(
    request: Request,
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> ScenarioService:
    nats_client = getattr(request.app.state, "nats_client", None)
    nats_config = getattr(request.app.state, "nats_config", None)
    outbound_subject = (
        nats_config.support_outbound_subject
        if nats_config is not None
        else SUPPORT_OUTBOUND_SUBJECT
    )
    return ScenarioService(session, nats_client=nats_client, outbound_subject=outbound_subject)
