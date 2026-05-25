from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.config import get_settings
from services.notifications.schemas import (
    NodeDownEvent,
    NotificationEventAdapter,
    PurchaseEvent,
)
from services.notifications.service import NotificationService


@pytest.mark.asyncio
async def test_publish_no_op_when_nats_missing():
    service = NotificationService(None)
    await service.publish_user_registered(telegram_id=1, username="u")


@pytest.mark.asyncio
async def test_publish_no_op_when_nats_disconnected():
    nats = MagicMock()
    nats.is_connected = False
    service = NotificationService(nats)
    await service.publish_purchase(
        telegram_id=1, username="u", plan_name="Plan",
        amount_rub=100.0, provider="test", is_renewal=False,
    )
    nats.publish_jetstream.assert_not_called()


@pytest.mark.asyncio
async def test_publish_node_down_emits_jetstream_with_dedup_id():
    nats = MagicMock()
    nats.is_connected = True
    nats.ensure_stream = AsyncMock()
    nats.publish_jetstream = AsyncMock()

    service = NotificationService(nats)
    last_seen = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    await service.publish_node_down(
        node_id="n1", node_name="spb-01",
        last_seen_at=last_seen, affected_placements=5,
    )

    nats.publish_jetstream.assert_called_once()
    kwargs = nats.publish_jetstream.call_args.kwargs
    assert kwargs["subject"] == get_settings().nats.notifications_subject
    assert kwargs["msg_id"].startswith("node_down:")
    payload = kwargs["payload"]
    assert payload["kind"] == "node_down"
    assert payload["node_id"] == "n1"
    assert payload["affected_placements"] == 5


@pytest.mark.asyncio
async def test_publisher_payload_is_consumer_valid():
    nats = MagicMock()
    nats.is_connected = True
    nats.ensure_stream = AsyncMock()
    nats.publish_jetstream = AsyncMock()

    service = NotificationService(nats)
    await service.publish_purchase(
        telegram_id=42, username="alice", plan_name="Месяц",
        amount_rub=599, provider="FreeKassa", is_renewal=True,
    )

    payload = nats.publish_jetstream.call_args.kwargs["payload"]
    event = NotificationEventAdapter.validate_python(payload)
    assert isinstance(event, PurchaseEvent)
    assert event.is_renewal is True
    assert event.amount_rub == 599


@pytest.mark.asyncio
async def test_publish_swallows_nats_errors():
    nats = MagicMock()
    nats.is_connected = True
    nats.ensure_stream = AsyncMock()
    nats.publish_jetstream = AsyncMock(side_effect=RuntimeError("boom"))

    service = NotificationService(nats)
    await service.publish_user_registered(telegram_id=1, username="u")


def test_schemas_have_unique_kinds():
    seen = set()
    for variant in [
        NodeDownEvent,
        PurchaseEvent,
    ]:
        kind = variant.model_fields["kind"].default
        assert kind not in seen
        seen.add(kind)
