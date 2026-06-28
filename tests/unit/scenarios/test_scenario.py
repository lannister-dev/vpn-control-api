from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.scenarios.constants import ScenarioStatus
from services.scenarios.service import ScenarioService, ScenarioUserNotReady


def _svc() -> ScenarioService:
    svc = ScenarioService(MagicMock(), nats_client=AsyncMock(), outbound_subject="out")
    svc.scenarios = AsyncMock()
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
        current_node_key=current, node_sends=0, status=ScenarioStatus.ACTIVE,
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
    svc.scenarios.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    state = _state("m1")

    ok = await svc._process_state(state, now=datetime.now(timezone.utc))

    assert ok is True
    svc._nats.publish_jetstream.assert_awaited_once()
    assert state.current_node_key == "m2"
    assert state.status == ScenarioStatus.ACTIVE
    assert state.next_send_at is not None


async def test_message_repeats_until_cap_then_advances():
    svc = _svc()
    camp = _campaign(
        [_node("m1", delay=0, repeat=3, interval=86400), _node("end", "end")],
        [_edge("m1", "end")], entry="m1",
    )
    svc.scenarios.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    state = _state("m1")

    # first two ticks: send + stay on the same node (reminder repeats)
    await svc._process_state(state, now=datetime.now(timezone.utc))
    assert state.current_node_key == "m1" and state.node_sends == 1
    assert state.status == ScenarioStatus.ACTIVE
    await svc._process_state(state, now=datetime.now(timezone.utc))
    assert state.current_node_key == "m1" and state.node_sends == 2
    # third tick: cap reached → advance to end → completed
    await svc._process_state(state, now=datetime.now(timezone.utc))
    assert state.node_sends == 3
    assert state.status == ScenarioStatus.COMPLETED
    assert svc._nats.publish_jetstream.await_count == 3


async def test_repeat_stops_when_gate_resolves():
    svc = _svc()
    camp = _campaign(
        [_node("m1", delay=0, condition="not_connected", repeat=5, interval=86400), _node("end", "end")],
        [_edge("m1", "end")], entry="m1",
    )
    svc.scenarios.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    svc.scenarios.has_connected = AsyncMock(return_value=False)  # not connected → reminder fires
    state = _state("m1")
    await svc._process_state(state, now=datetime.now(timezone.utc))
    assert state.node_sends == 1 and state.status == ScenarioStatus.ACTIVE

    svc.scenarios.has_connected = AsyncMock(return_value=True)  # user connected → gate fails
    await svc._process_state(state, now=datetime.now(timezone.utc))
    assert state.status == ScenarioStatus.COMPLETED
    assert svc._nats.publish_jetstream.await_count == 1  # no further reminder


async def test_message_gate_fail_completes_without_send():
    svc = _svc()
    camp = _campaign([_node("m1", condition="not_connected"), _node("end", "end")],
                     [_edge("m1", "end")], entry="m1")
    svc.scenarios.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    svc.scenarios.has_connected = AsyncMock(return_value=True)  # already connected → gate fails
    state = _state("m1")

    ok = await svc._process_state(state, now=datetime.now(timezone.utc))

    assert ok is False
    svc._nats.publish_jetstream.assert_not_awaited()
    assert state.status == ScenarioStatus.COMPLETED


async def test_condition_node_routes_by_branch():
    svc = _svc()
    camp = _campaign(
        [_node("c1", "condition", check="connected"),
         _node("yes", delay=60), _node("no", delay=60), _node("end", "end")],
        [_edge("c1", "yes", "yes"), _edge("c1", "no", "no"),
         _edge("yes", "end"), _edge("no", "end")],
        entry="c1",
    )
    svc.scenarios.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    svc.scenarios.has_connected = AsyncMock(return_value=True)  # connected → "yes" branch
    state = _state("c1")

    ok = await svc._process_state(state, now=datetime.now(timezone.utc))

    assert ok is False  # condition routes, no send
    svc._nats.publish_jetstream.assert_not_awaited()
    assert state.current_node_key == "yes"  # waiting at the yes-branch message
    assert state.status == ScenarioStatus.ACTIVE


async def test_end_node_completes():
    svc = _svc()
    camp = _campaign([_node("end", "end")], [], entry="end")
    svc.scenarios.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    state = _state("end")

    ok = await svc._process_state(state, now=datetime.now(timezone.utc))

    assert ok is False
    assert state.status == ScenarioStatus.COMPLETED


async def test_opt_out_stops():
    svc = _svc()
    camp = _campaign([_node("m1")], [], entry="m1")
    svc.scenarios.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user(supp=True))
    state = _state("m1")

    ok = await svc._process_state(state, now=datetime.now(timezone.utc))

    assert ok is False
    assert state.status == ScenarioStatus.STOPPED
    svc._nats.publish_jetstream.assert_not_awaited()


async def test_last_message_completes():
    svc = _svc()
    camp = _campaign([_node("m1")], [], entry="m1")  # no outgoing edge
    svc.scenarios.get_campaign_with_graph = AsyncMock(return_value=camp)
    svc.users.get_by_id = AsyncMock(return_value=_user())
    state = _state("m1")

    ok = await svc._process_state(state, now=datetime.now(timezone.utc))

    assert ok is True
    assert state.status == ScenarioStatus.COMPLETED
    assert state.next_send_at is None


async def test_enroll_uses_entry_node():
    svc = _svc()
    camp = _campaign([_node("m1", delay=3600)], [], entry="m1")
    svc.scenarios.active_campaigns_by_trigger = AsyncMock(return_value=[camp])
    svc.users.get_by_telegram_id = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    svc.scenarios.enroll = AsyncMock(return_value=True)

    n = await svc.enroll_for_event(event_kind="trial_started", telegram_id=1)

    assert n == 1
    _, kwargs = svc.scenarios.enroll.call_args
    assert kwargs["current_node_key"] == "m1"


def test_node_schema_rejects_bad_type_and_condition():
    import pytest
    from pydantic import ValidationError

    from services.scenarios.schemas import ScenarioNodeIn

    with pytest.raises(ValidationError):
        ScenarioNodeIn(key="m1", type="bogus")
    with pytest.raises(ValidationError):
        ScenarioNodeIn(key="m1", type="message", condition="bogus")


def test_campaign_schema_parses_nodes_and_edges():
    from services.scenarios.schemas import ScenarioCampaignIn

    c = ScenarioCampaignIn(
        key="trial_connect", name="x", trigger_event="trial_started",
        nodes=[{"key": "m1", "type": "message", "condition": "not_connected"}],
        edges=[{"from": "m1", "to": "end"}],
    )
    assert c.nodes[0].key == "m1"
    assert c.edges[0].from_node == "m1" and c.edges[0].to_node == "end"


def test_render_text_substitutes_vars():
    user = SimpleNamespace(username="vasya", referral_code="ABC")
    out = ScenarioService._render_text("Привет, {name}! Зови друзей: {referral}", user)
    assert "vasya" in out
    assert "{name}" not in out
    assert "{referral}" not in out


def test_render_text_name_dropped_when_no_username():
    user = SimpleNamespace(username=None, telegram_id=420200363)
    assert ScenarioService._render_text("Привет, {name}!", user) == "Привет!"
    assert ScenarioService._render_text("{name}, смотри", user) == "смотри"
    assert ScenarioService._render_text("Эй {name}!", user) == "Эй!"


def test_build_outbound_button_action_vs_url():
    a = ScenarioService._build_outbound_button({"text": "Продлить", "action": "renew", "style": "success"})
    assert a.action == "renew" and a.url == "" and a.style == "success"
    u = ScenarioService._build_outbound_button({"text": "Сайт", "url": "https://x.com"})
    assert u.url == "https://x.com" and u.action is None
    assert ScenarioService._build_outbound_button({"text": "X", "action": "bogus"}) is None


async def test_stats_aggregates_by_status():
    svc = _svc()
    cid = uuid4()
    svc.scenarios.status_counts = AsyncMock(
        return_value=[(cid, "active", 3), (cid, "completed", 2), (cid, "stopped", 1)]
    )
    out = await svc.stats()
    assert len(out.items) == 1
    assert out.items[0].active == 3 and out.items[0].enrolled == 6


async def test_enroll_raises_user_not_ready_when_user_missing_but_campaign_active():
    svc = _svc()
    svc.scenarios.active_campaigns_by_trigger = AsyncMock(return_value=[object()])
    svc.users.get_by_telegram_id = AsyncMock(return_value=None)
    with pytest.raises(ScenarioUserNotReady):
        await svc.enroll_for_event(event_kind="user_registered", telegram_id=42)


async def test_enroll_returns_zero_when_no_campaigns():
    svc = _svc()
    svc.scenarios.active_campaigns_by_trigger = AsyncMock(return_value=[])
    svc.users.get_by_telegram_id = AsyncMock(return_value=None)
    assert await svc.enroll_for_event(event_kind="user_registered", telegram_id=42) == 0
    svc.users.get_by_telegram_id.assert_not_awaited()


def test_build_outbound_button_promo_carries_code():
    btn = ScenarioService._build_outbound_button({"text": "Скидка", "action": "promo", "value": "SALE30"})
    assert btn is not None
    assert btn.action == "promo" and btn.value == "SALE30"


def test_build_outbound_button_promo_without_code_is_dropped():
    assert ScenarioService._build_outbound_button({"text": "Скидка", "action": "promo", "value": ""}) is None
