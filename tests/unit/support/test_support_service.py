from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.support.schemas import (
    MessageSenderKind,
    TicketCategory,
    TicketCreateIn,
    TicketPatchIn,
    TicketPriority,
    TicketStatus,
)


def _ticket(**overrides):
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        subject="hello",
        status=TicketStatus.NEW.value,
        priority=TicketPriority.NORMAL.value,
        category=TicketCategory.OTHER.value,
        assignee_admin_id=None,
        last_activity_at=datetime.now(timezone.utc),
        closed_at=None,
        first_user_msg_at=None,
        first_reply_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_active=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_patch_ticket_close_sets_closed_at(monkeypatch):
    from services.support.service import SupportService

    session = SimpleNamespace(
        flush=lambda: None,
        commit=lambda: None,
        execute=lambda *a, **kw: None,
    )
    svc = SupportService.__new__(SupportService)
    svc.session = session

    t = _ticket()
    svc.tickets = SimpleNamespace(get_by_id=_async_return(t))
    svc._fetch_users_with_meta = _async_return({})
    svc.messages = SimpleNamespace(
        has_media_flags=_async_return({}),
        create=_async_return(SimpleNamespace(id=None, ticket_id=t.id)),
    )
    svc.admins = SimpleNamespace(list_usernames_by_ids=_async_return({}))
    svc._resolve_admin_id = _async_return(None)
    svc._publish_outbound = _async_return(None)

    async def _flush():
        return None

    async def _commit():
        return None

    session.flush = _flush
    session.commit = _commit

    out = await svc.patch_ticket(
        t.id, TicketPatchIn(status=TicketStatus.CLOSED), actor_admin_id=None
    )
    assert t.status == TicketStatus.CLOSED.value
    assert t.closed_at is not None
    assert out.status == TicketStatus.CLOSED


def _async_return(val):
    async def _f(*a, **kw):
        return val

    return _f


def test_subject_truncation_constant():
    from services.support.constants import SUBJECT_PREVIEW_LEN

    assert SUBJECT_PREVIEW_LEN == 80


def test_ticket_create_schema_defaults():
    data = TicketCreateIn(user_id=uuid4())
    assert data.category == TicketCategory.OTHER
    assert data.priority == TicketPriority.NORMAL
    assert data.subject == ""


def test_message_sender_enum():
    assert MessageSenderKind("user") == MessageSenderKind.USER
    assert MessageSenderKind("operator") == MessageSenderKind.OPERATOR
    assert MessageSenderKind("system") == MessageSenderKind.SYSTEM


def _claimed_broadcast(**overrides):
    base = dict(
        id=uuid4(), audience="all", plan_id=None, text_body="hi",
        media_kind=None, media_url=None, inline_buttons=None, attempts=0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _bc_service(*, delivered: int, claimed):
    from unittest.mock import AsyncMock

    from services.support.service import SupportService
    svc = SupportService.__new__(SupportService)
    svc.session = AsyncMock()
    svc.broadcasts = AsyncMock()
    svc.broadcasts.claim_for_send = AsyncMock(return_value=claimed)
    svc._resolve_audience = AsyncMock(return_value=[uuid4()])
    svc._fan_out_broadcast = AsyncMock(return_value=delivered)
    return svc


@pytest.mark.asyncio
async def test_broadcast_zero_delivered_reschedules():
    claimed = _claimed_broadcast(attempts=0)
    svc = _bc_service(delivered=0, claimed=claimed)
    ok = await svc.send_scheduled_broadcast(claimed.id)
    assert ok is False
    svc.broadcasts.reschedule_for_retry.assert_awaited_once()
    assert svc.broadcasts.reschedule_for_retry.await_args.kwargs["attempts"] == 1
    svc.broadcasts.mark_sent.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_delivered_marks_sent():
    claimed = _claimed_broadcast()
    svc = _bc_service(delivered=5, claimed=claimed)
    ok = await svc.send_scheduled_broadcast(claimed.id)
    assert ok is True
    svc.broadcasts.mark_sent.assert_awaited_once()
    svc.broadcasts.reschedule_for_retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_exhausted_marks_failed():
    from services.support.constants import MAX_BROADCAST_DISPATCH_ATTEMPTS
    claimed = _claimed_broadcast(attempts=MAX_BROADCAST_DISPATCH_ATTEMPTS - 1)
    svc = _bc_service(delivered=0, claimed=claimed)
    ok = await svc.send_scheduled_broadcast(claimed.id)
    assert ok is False
    svc.broadcasts.mark_failed.assert_awaited_once()
    svc.broadcasts.reschedule_for_retry.assert_not_awaited()


def test_next_run_daily():
    from datetime import datetime, timezone

    from services.support.service import SupportService
    after = datetime(2026, 6, 13, 10, 0, tzinfo=timezone.utc)
    # 08:00 already passed today → tomorrow
    assert SupportService._compute_next_run("daily", "08:00", None, after) == datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc)
    # 18:00 still ahead today
    assert SupportService._compute_next_run("daily", "18:00", None, after) == datetime(2026, 6, 13, 18, 0, tzinfo=timezone.utc)


def test_next_run_weekly():
    from datetime import datetime, timezone

    from services.support.service import SupportService
    after = datetime(2026, 6, 13, 10, 0, tzinfo=timezone.utc)
    nxt = SupportService._compute_next_run("weekly", "09:00", [0], after)
    assert nxt.weekday() == 0 and nxt.hour == 9 and nxt > after


@pytest.mark.asyncio
async def test_materialize_recurring_dispatches():
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from services.support.service import SupportService
    svc = SupportService.__new__(SupportService)
    svc.session = AsyncMock()
    sched = SimpleNamespace(
        id=uuid4(), text_body="hi", promo_code_id=None, audience="all", plan_id=None,
        inline_buttons=None, media_kind=None, media_url=None,
        cadence="daily", time_of_day="08:00", weekdays=None, created_by_admin_id=None,
    )
    svc.recurring = AsyncMock()
    svc.recurring.list_due = AsyncMock(return_value=[sched])
    svc.recurring.update_by_id = AsyncMock()
    svc.create_broadcast = AsyncMock()
    n = await svc.materialize_due_recurring(datetime(2026, 6, 13, 10, 0, tzinfo=timezone.utc))
    assert n == 1
    svc.create_broadcast.assert_awaited_once()
    upd = svc.recurring.update_by_id.await_args.args[1]
    assert "next_run_at" in upd and "last_run_at" in upd


def test_inbound_message_parses_custom_emoji_entities():
    from services.support.schemas import SupportInboundMessage

    m = SupportInboundMessage.model_validate(
        {
            "telegram_id": 1,
            "text": "hi",
            "entities": [
                {"type": "custom_emoji", "offset": 0, "length": 2, "custom_emoji_id": "555"}
            ],
        }
    )
    assert m.entities[0].type == "custom_emoji"
    assert m.entities[0].custom_emoji_id == "555"


@pytest.mark.asyncio
async def test_fan_out_includes_entities_when_present():
    from unittest.mock import AsyncMock

    from services.support.service import SupportService

    svc = SupportService.__new__(SupportService)
    svc._nats = AsyncMock()
    svc._outbound_subject = "support.message.out"
    svc._ensure_outbound_stream = AsyncMock()
    uid = uuid4()
    svc.users = AsyncMock()
    svc.users.list_by_ids = AsyncMock(
        return_value=[SimpleNamespace(id=uid, telegram_id=111)]
    )
    ent = [{"type": "custom_emoji", "offset": 0, "length": 2, "custom_emoji_id": "555"}]
    bcast = SimpleNamespace(id=uuid4(), promo_code_id=None, entities=ent)
    svc.broadcasts = AsyncMock()
    svc.broadcasts.get_by_id = AsyncMock(return_value=bcast)

    n = await svc._fan_out_broadcast(bcast.id, [uid], "hi")
    assert n == 1
    payload = svc._nats.publish_jetstream.await_args.kwargs["payload"]
    assert len(payload["entities"]) == 1
    assert payload["entities"][0]["custom_emoji_id"] == "555"
    assert payload["parse_mode"] is None


@pytest.mark.asyncio
async def test_fan_out_html_parse_mode_without_entities():
    from unittest.mock import AsyncMock

    from services.support.service import SupportService

    svc = SupportService.__new__(SupportService)
    svc._nats = AsyncMock()
    svc._outbound_subject = "support.message.out"
    svc._ensure_outbound_stream = AsyncMock()
    uid = uuid4()
    svc.users = AsyncMock()
    svc.users.list_by_ids = AsyncMock(
        return_value=[SimpleNamespace(id=uid, telegram_id=111)]
    )
    bcast = SimpleNamespace(id=uuid4(), promo_code_id=None, entities=None)
    svc.broadcasts = AsyncMock()
    svc.broadcasts.get_by_id = AsyncMock(return_value=bcast)

    n = await svc._fan_out_broadcast(bcast.id, [uid], "hi")
    assert n == 1
    payload = svc._nats.publish_jetstream.await_args.kwargs["payload"]
    assert payload["entities"] is None
    assert payload["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_emoji_resolver_noop_without_config():
    from services.support.emoji_assets import CustomEmojiResolver

    support = SimpleNamespace(bot_token="", media_proxy_timeout_sec=5)
    s3 = SimpleNamespace(enabled=False)
    resolver = CustomEmojiResolver(support=support, s3=s3)
    assert await resolver.resolve(["1", "2"]) == {}
    assert await resolver.resolve([]) == {}


@pytest.mark.asyncio
async def test_emoji_resolver_builds_map():
    from unittest.mock import AsyncMock

    from services.support.emoji_assets import CustomEmojiResolver

    support = SimpleNamespace(bot_token="t", media_proxy_timeout_sec=5)
    s3 = SimpleNamespace(enabled=True, region="", addressing_style="virtual")
    resolver = CustomEmojiResolver(support=support, s3=s3)
    resolver._get_custom_emoji_stickers = AsyncMock(
        return_value=[{"custom_emoji_id": "555", "thumbnail": {"file_id": "fid"}}]
    )
    resolver._download_and_upload = AsyncMock(return_value="https://cdn/emoji/555.webp")

    out = await resolver.resolve(["555", "555"])
    assert out == {"555": "https://cdn/emoji/555.webp"}


@pytest.mark.asyncio
async def test_admin_message_creates_draft_with_entities(monkeypatch):
    from unittest.mock import AsyncMock

    import services.support.consumer as consumer_mod
    from services.support.consumer import SupportInboundConsumer
    from services.support.schemas import SupportInboundMessage

    captured: dict = {}

    async def fake_create_broadcast(self, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(consumer_mod.SupportService, "create_broadcast", fake_create_broadcast)
    monkeypatch.setattr(
        consumer_mod.CustomEmojiResolver, "resolve", AsyncMock(return_value={"555": "u"})
    )

    cons = SupportInboundConsumer.__new__(SupportInboundConsumer)
    cons._nats = AsyncMock()
    cons._config = SimpleNamespace(support_outbound_subject="support.message.out")
    parsed = SupportInboundMessage.model_validate(
        {
            "telegram_id": 1,
            "text": "hi",
            "entities": [
                {"type": "custom_emoji", "offset": 0, "length": 2, "custom_emoji_id": "555"}
            ],
        }
    )
    admin_id = uuid4()
    await cons._ingest_admin_broadcast_draft(AsyncMock(), admin_id=admin_id, parsed=parsed)

    assert captured["actor_admin_id"] == admin_id
    assert captured["status"].value == "draft"
    assert captured["entities"] is None
    assert '<tg-emoji emoji-id="555">' in captured["text"]
    assert captured["custom_emoji_assets"] == {"555": "u"}


def test_custom_emoji_entities_to_html():
    from services.support.emoji_assets import custom_emoji_entities_to_html

    ent = [SimpleNamespace(type="custom_emoji", offset=6, length=2, custom_emoji_id="555")]
    out = custom_emoji_entities_to_html("Hello 🔥 world", ent)
    assert '<tg-emoji emoji-id="555">🔥</tg-emoji>' in out
    assert out.startswith("Hello ") and out.endswith(" world")


def test_custom_emoji_entities_to_html_escapes_plain():
    from services.support.emoji_assets import custom_emoji_entities_to_html

    out = custom_emoji_entities_to_html("a < b & c", [])
    assert out == "a &lt; b &amp; c"


@pytest.mark.asyncio
async def test_fan_out_button_style():
    from unittest.mock import AsyncMock

    from services.support.service import SupportService

    svc = SupportService.__new__(SupportService)
    svc._nats = AsyncMock()
    svc._outbound_subject = "support.message.out"
    svc._ensure_outbound_stream = AsyncMock()
    uid = uuid4()
    svc.users = AsyncMock()
    svc.users.list_by_ids = AsyncMock(return_value=[SimpleNamespace(id=uid, telegram_id=111)])
    bcast = SimpleNamespace(id=uuid4(), promo_code_id=None, entities=None)
    svc.broadcasts = AsyncMock()
    svc.broadcasts.get_by_id = AsyncMock(return_value=bcast)

    buttons = [
        {"text": "Buy", "url": "https://x", "style": "danger"},
        {"text": "More", "url": "https://y", "style": "bogus"},
    ]
    n = await svc._fan_out_broadcast(bcast.id, [uid], "hi", buttons=buttons)
    assert n == 1
    payload = svc._nats.publish_jetstream.await_args.kwargs["payload"]
    btns = payload["buttons"]
    assert btns[0]["style"] == "danger"
    assert btns[1]["style"] is None


def test_is_valid_button_url():
    from services.support.service import SupportService

    f = SupportService._is_valid_button_url
    assert f("https://example.com") is True
    assert f("https://t.me/foo") is True
    assert f("tg://resolve?domain=foo") is True
    assert f("http://") is False
    assert f("") is False
    assert f("notaurl") is False
    assert f("ftp://x.com") is False


def test_strip_html_text_normalizes():
    from services.support.service import SupportService

    f = SupportService._strip_html_text
    a = f('<tg-emoji emoji-id="1">🌍</tg-emoji> Факт\r\nстрока')
    b = f('🌍 Факт\nстрока')
    assert a == b == "🌍 Факт строка"
