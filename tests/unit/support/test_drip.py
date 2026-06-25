from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from services.support.constants import DripStatus
from services.support.service import SupportService


def _svc() -> SupportService:
    svc = SupportService(MagicMock(), nats_client=AsyncMock(), outbound_subject="out")
    svc.drip = AsyncMock()
    svc.users = AsyncMock()
    return svc


def _node(key, type="message", *, delay=0, condition="always", check=None, text="hi", repeat=1, interval=0):
    return SimpleNamespace(
        node_key=key, node_type=type, delay_seconds=delay, condition=condition,
        repeat_count=repeat, repeat_interval_sec=interval,
        text_body=text, inline_buttons=None, media_kind=None, media_url=None,
        check_kind=check, conversion=False, label=None, pos_cx=0, pos_top=0, id=uuid4(),
    )


def _edge(frm, to, branch=None):
    return SimpleNamespace(from_key=frm, to_key=to, branch=branch)


def _campaign(nodes, edges, *, entry, is_active=True):
    return SimpleNamespace(
        id=uuid4(), key="k", name="n", trigger_event="trial_started",
        is_active=is_active, entry_node_key=entry, nodes=nodes, edges=edges,
    )


def _state(current):
    return SimpleNamespace(
        id=uuid4(), campaign_id=uuid4(), user_id=uuid4(),
        current_node_key=current, node_sends=0, status=DripStatus.ACTIVE,
        next_send_at=datetime.now(timezone.utc), last_step_sent_at=None,
    )


def _user(**kw):
    return SimpleNamespace(telegram_id=kw.get("tg", 1), suppress_marketing=kw.get("supp", False))


async def test_message_sends_and_advances_to_next_message():
    svc = _svc()
    camp = _campaign(
        [_node("m1", delay=0), _node("m2", delay=7200), _node("end", "end")],
        [_edge("m1", "m2"), _edge("m2", "end")],
        entry="m1",
    )
    svc.drip.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    state = _state("m1")

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is True
    svc._nats.publish_jetstream.assert_awaited_once()
    assert state.current_node_key == "m2"
    assert state.status == DripStatus.ACTIVE
    assert state.next_send_at is not None


async def test_message_repeats_until_cap_then_advances():
    svc = _svc()
    camp = _campaign(
        [_node("m1", delay=0, repeat=3, interval=86400), _node("end", "end")],
        [_edge("m1", "end")], entry="m1",
    )
    svc.drip.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    state = _state("m1")

    # first two ticks: send + stay on the same node (reminder repeats)
    await svc._process_drip_state(state, now=datetime.now(timezone.utc))
    assert state.current_node_key == "m1" and state.node_sends == 1
    assert state.status == DripStatus.ACTIVE
    await svc._process_drip_state(state, now=datetime.now(timezone.utc))
    assert state.current_node_key == "m1" and state.node_sends == 2
    # third tick: cap reached → advance to end → completed
    await svc._process_drip_state(state, now=datetime.now(timezone.utc))
    assert state.node_sends == 3
    assert state.status == DripStatus.COMPLETED
    assert svc._nats.publish_jetstream.await_count == 3


async def test_repeat_stops_when_gate_resolves():
    svc = _svc()
    camp = _campaign(
        [_node("m1", delay=0, condition="not_connected", repeat=5, interval=86400), _node("end", "end")],
        [_edge("m1", "end")], entry="m1",
    )
    svc.drip.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    svc.drip.has_connected = AsyncMock(return_value=False)  # not connected → reminder fires
    state = _state("m1")
    await svc._process_drip_state(state, now=datetime.now(timezone.utc))
    assert state.node_sends == 1 and state.status == DripStatus.ACTIVE

    svc.drip.has_connected = AsyncMock(return_value=True)  # user connected → gate fails
    await svc._process_drip_state(state, now=datetime.now(timezone.utc))
    assert state.status == DripStatus.COMPLETED
    assert svc._nats.publish_jetstream.await_count == 1  # no further reminder


async def test_message_gate_fail_completes_without_send():
    svc = _svc()
    camp = _campaign([_node("m1", condition="not_connected"), _node("end", "end")],
                     [_edge("m1", "end")], entry="m1")
    svc.drip.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    svc.drip.has_connected = AsyncMock(return_value=True)  # already connected → gate fails
    state = _state("m1")

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is False
    svc._nats.publish_jetstream.assert_not_awaited()
    assert state.status == DripStatus.COMPLETED


async def test_condition_node_routes_by_branch():
    svc = _svc()
    camp = _campaign(
        [_node("c1", "condition", check="connected"),
         _node("yes", delay=60), _node("no", delay=60), _node("end", "end")],
        [_edge("c1", "yes", "yes"), _edge("c1", "no", "no"),
         _edge("yes", "end"), _edge("no", "end")],
        entry="c1",
    )
    svc.drip.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    svc.drip.has_connected = AsyncMock(return_value=True)  # connected → "yes" branch
    state = _state("c1")

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is False  # condition routes, no send
    svc._nats.publish_jetstream.assert_not_awaited()
    assert state.current_node_key == "yes"  # waiting at the yes-branch message
    assert state.status == DripStatus.ACTIVE


async def test_end_node_completes():
    svc = _svc()
    camp = _campaign([_node("end", "end")], [], entry="end")
    svc.drip.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    state = _state("end")

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is False
    assert state.status == DripStatus.COMPLETED


async def test_opt_out_stops():
    svc = _svc()
    camp = _campaign([_node("m1")], [], entry="m1")
    svc.drip.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user(supp=True))
    state = _state("m1")

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is False
    assert state.status == DripStatus.STOPPED
    svc._nats.publish_jetstream.assert_not_awaited()


async def test_last_message_completes():
    svc = _svc()
    camp = _campaign([_node("m1")], [], entry="m1")  # no outgoing edge
    svc.drip.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    state = _state("m1")

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is True
    assert state.status == DripStatus.COMPLETED
    assert state.next_send_at is None


async def test_enroll_uses_entry_node():
    svc = _svc()
    camp = _campaign([_node("m1", delay=3600)], [], entry="m1")
    svc.drip.active_campaigns_by_trigger = AsyncMock(return_value=[camp])
    svc.users.get_by_telegram_id = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    svc.drip.enroll = AsyncMock(return_value=True)

    n = await svc.enroll_drip_for_event(event_kind="trial_started", telegram_id=1)

    assert n == 1
    _, kwargs = svc.drip.enroll.call_args
    assert kwargs["current_node_key"] == "m1"


def test_node_schema_rejects_bad_type_and_condition():
    import pytest
    from pydantic import ValidationError

    from services.support.schemas import DripNodeIn

    with pytest.raises(ValidationError):
        DripNodeIn(key="m1", type="bogus")
    with pytest.raises(ValidationError):
        DripNodeIn(key="m1", type="message", condition="bogus")


def test_campaign_schema_parses_nodes_and_edges():
    from services.support.schemas import DripCampaignIn

    c = DripCampaignIn(
        key="trial_connect", name="x", trigger_event="trial_started",
        nodes=[{"key": "m1", "type": "message", "condition": "not_connected"}],
        edges=[{"from": "m1", "to": "end"}],
    )
    assert c.nodes[0].key == "m1"
    assert c.edges[0].from_node == "m1" and c.edges[0].to_node == "end"


def test_render_drip_text_substitutes_vars():
    user = SimpleNamespace(username="vasya", referral_code="ABC")
    out = SupportService._render_drip_text("Привет, {name}! Зови друзей: {referral}", user)
    assert "vasya" in out
    assert "{name}" not in out
    assert "{referral}" not in out


def test_build_outbound_button_action_vs_url():
    a = SupportService._build_outbound_button({"text": "Продлить", "action": "renew", "style": "success"})
    assert a.action == "renew" and a.url == "" and a.style == "success"
    u = SupportService._build_outbound_button({"text": "Сайт", "url": "https://x.com"})
    assert u.url == "https://x.com" and u.action is None
    assert SupportService._build_outbound_button({"text": "X", "action": "bogus"}) is None


async def test_drip_stats_aggregates_by_status():
    svc = _svc()
    cid = uuid4()
    svc.drip.status_counts = AsyncMock(
        return_value=[(cid, "active", 3), (cid, "completed", 2), (cid, "stopped", 1)]
    )
    out = await svc.drip_stats()
    assert len(out.items) == 1
    assert out.items[0].active == 3 and out.items[0].enrolled == 6
