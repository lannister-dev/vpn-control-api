from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from services.support.constants import DripCondition, DripStatus
from services.support.service import SupportService


def _svc() -> SupportService:
    svc = SupportService(MagicMock(), nats_client=AsyncMock(), outbound_subject="out")
    svc.drip = AsyncMock()
    svc.users = AsyncMock()
    return svc


def _step(order: int = 0, delay: int = 0, condition: str = DripCondition.ALWAYS):
    return SimpleNamespace(
        step_order=order,
        delay_seconds=delay,
        condition=condition,
        text_body="hi",
        inline_buttons=None,
        media_kind=None,
        media_url=None,
    )


def _state(step: int = 0):
    return SimpleNamespace(
        id=uuid4(),
        campaign_id=uuid4(),
        user_id=uuid4(),
        current_step=step,
        status=DripStatus.ACTIVE,
        next_send_at=datetime.now(timezone.utc),
        last_step_sent_at=None,
    )


async def test_enroll_drip_enrolls_each_campaign():
    svc = _svc()
    campaign = SimpleNamespace(id=uuid4(), steps=[_step(0, delay=3600)])
    svc.drip.active_campaigns_by_trigger = AsyncMock(return_value=[campaign])
    svc.users.get_by_telegram_id = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    svc.drip.enroll = AsyncMock(return_value=True)

    enrolled = await svc.enroll_drip_for_event(event_kind="trial_started", telegram_id=1)

    assert enrolled == 1
    svc.drip.enroll.assert_awaited_once()


async def test_enroll_drip_no_user_is_noop():
    svc = _svc()
    svc.drip.active_campaigns_by_trigger = AsyncMock(
        return_value=[SimpleNamespace(id=uuid4(), steps=[_step()])]
    )
    svc.users.get_by_telegram_id = AsyncMock(return_value=None)

    assert await svc.enroll_drip_for_event(event_kind="purchase", telegram_id=9) == 0


async def test_drip_sends_when_condition_holds_and_advances():
    svc = _svc()
    state = _state(0)
    campaign = SimpleNamespace(
        is_active=True,
        steps=[_step(0, condition=DripCondition.NOT_CONNECTED), _step(1, delay=7200)],
    )
    svc.drip.get_campaign_with_steps = AsyncMock(return_value=campaign)
    svc.users.get_by_id = AsyncMock(
        return_value=SimpleNamespace(telegram_id=123, suppress_marketing=False)
    )
    svc.drip.has_connected = AsyncMock(return_value=False)

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is True
    svc._nats.publish_jetstream.assert_awaited_once()
    assert state.current_step == 1
    assert state.status == DripStatus.ACTIVE
    assert state.next_send_at is not None


async def test_drip_completes_when_condition_fails():
    svc = _svc()
    state = _state(0)
    campaign = SimpleNamespace(
        is_active=True, steps=[_step(0, condition=DripCondition.NOT_CONNECTED)]
    )
    svc.drip.get_campaign_with_steps = AsyncMock(return_value=campaign)
    svc.users.get_by_id = AsyncMock(
        return_value=SimpleNamespace(telegram_id=1, suppress_marketing=False)
    )
    svc.drip.has_connected = AsyncMock(return_value=True)

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is False
    svc._nats.publish_jetstream.assert_not_awaited()
    assert state.status == DripStatus.COMPLETED


async def test_drip_stops_on_opt_out():
    svc = _svc()
    state = _state(0)
    campaign = SimpleNamespace(is_active=True, steps=[_step(0)])
    svc.drip.get_campaign_with_steps = AsyncMock(return_value=campaign)
    svc.users.get_by_id = AsyncMock(
        return_value=SimpleNamespace(telegram_id=1, suppress_marketing=True)
    )

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is False
    assert state.status == DripStatus.STOPPED
    svc._nats.publish_jetstream.assert_not_awaited()


async def test_drip_last_step_completes():
    svc = _svc()
    state = _state(0)
    campaign = SimpleNamespace(is_active=True, steps=[_step(0)])
    svc.drip.get_campaign_with_steps = AsyncMock(return_value=campaign)
    svc.users.get_by_id = AsyncMock(
        return_value=SimpleNamespace(telegram_id=5, suppress_marketing=False)
    )

    ok = await svc._process_drip_state(state, now=datetime.now(timezone.utc))

    assert ok is True
    assert state.current_step == 1
    assert state.status == DripStatus.COMPLETED
    assert state.next_send_at is None


def test_drip_step_rejects_bad_condition():
    import pytest
    from pydantic import ValidationError

    from services.support.schemas import DripStepIn

    with pytest.raises(ValidationError):
        DripStepIn(step_order=0, text_body="x", condition="bogus")


def test_drip_campaign_rejects_bad_trigger():
    import pytest
    from pydantic import ValidationError

    from services.support.schemas import DripCampaignIn

    with pytest.raises(ValidationError):
        DripCampaignIn(key="k", name="n", trigger_event="bogus")


def test_drip_campaign_accepts_valid():
    from services.support.schemas import DripCampaignIn, DripStepIn

    campaign = DripCampaignIn(
        key="trial_connect",
        name="x",
        trigger_event="trial_started",
        steps=[DripStepIn(step_order=0, text_body="hi", condition="not_connected")],
    )
    assert campaign.steps[0].condition == "not_connected"


async def test_list_drip_campaigns_maps_out():
    svc = _svc()
    campaign = SimpleNamespace(
        id=uuid4(),
        key="k",
        name="n",
        trigger_event="purchase",
        is_active=True,
        steps=[],
    )
    svc.drip.list_campaigns = AsyncMock(return_value=[campaign])

    out = await svc.list_drip_campaigns()

    assert len(out.items) == 1
    assert out.items[0].key == "k"


async def test_drip_stats_aggregates_by_status():
    svc = _svc()
    cid = uuid4()
    svc.drip.status_counts = AsyncMock(
        return_value=[(cid, "active", 3), (cid, "completed", 2), (cid, "stopped", 1)]
    )

    out = await svc.drip_stats()

    assert len(out.items) == 1
    item = out.items[0]
    assert item.campaign_id == cid
    assert item.active == 3
    assert item.completed == 2
    assert item.stopped == 1
    assert item.enrolled == 6


def test_render_drip_text_substitutes_vars():
    user = SimpleNamespace(username="vasya", referral_code="ABC")
    out = SupportService._render_drip_text("Привет, {name}! Зови друзей: {referral}", user)
    assert "vasya" in out
    assert "{name}" not in out
    assert "{referral}" not in out


def test_build_outbound_button_action_vs_url():
    action_btn = SupportService._build_outbound_button(
        {"text": "Продлить", "action": "renew", "style": "success"}
    )
    assert action_btn.action == "renew"
    assert action_btn.url == ""
    assert action_btn.style == "success"

    url_btn = SupportService._build_outbound_button({"text": "Сайт", "url": "https://x.com"})
    assert url_btn.url == "https://x.com"
    assert url_btn.action is None

    assert SupportService._build_outbound_button({"text": "X", "action": "bogus"}) is None
    assert SupportService._build_outbound_button({"action": "renew"}) is None
