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
    svc._fetch_admin_usernames = _async_return({})
    svc.messages = SimpleNamespace(has_media_flags=_async_return({}))
    svc._resolve_admin_id = _async_return(None)

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
