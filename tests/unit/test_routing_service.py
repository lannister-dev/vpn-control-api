from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.routing.service import RoutingService


def _node(*, region: str, capacity: int = 100):
    node = MagicMock()
    node.id = uuid4()
    node.region = region
    node.capacity = capacity
    return node


def _agent_state(*, is_healthy: bool = True, last_seen_at: datetime | None = None):
    state = MagicMock()
    state.is_healthy = is_healthy
    state.last_seen_at = last_seen_at or datetime.now(timezone.utc)
    return state


@pytest.mark.asyncio
async def test_select_nodes_filters_and_scores(async_session):
    svc = RoutingService(async_session)
    svc.repository = AsyncMock()

    strong = _node(region="fi", capacity=100)
    weak = _node(region="fi", capacity=100)
    unhealthy = _node(region="fi", capacity=100)
    full = _node(region="fi", capacity=10)

    svc.repository.list_available_nodes.return_value = [
        (weak, _agent_state(is_healthy=True), 90),
        (strong, _agent_state(is_healthy=True), 10),
        (unhealthy, _agent_state(is_healthy=False), 5),
        (full, _agent_state(is_healthy=True), 10),
    ]

    out = await svc.select_nodes(preferred_region="fi")

    assert out == [strong, weak]
    svc.repository.list_available_nodes.assert_awaited_once_with(
        preferred_region="fi",
        exclude_node_ids=None,
    )


@pytest.mark.asyncio
async def test_select_nodes_returns_empty(async_session):
    svc = RoutingService(async_session)
    svc.repository = AsyncMock()
    svc.repository.list_available_nodes.return_value = []

    out = await svc.select_nodes()

    assert out == []


@pytest.mark.asyncio
async def test_select_nodes_skips_stale_last_seen(async_session):
    svc = RoutingService(async_session)
    svc.repository = AsyncMock()
    svc.node_state_stale_after_sec = 90

    stale = _node(region="fi", capacity=100)
    fresh = _node(region="fi", capacity=100)
    svc.repository.list_available_nodes.return_value = [
        (
            stale,
            _agent_state(
                is_healthy=True,
                last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            ),
            1,
        ),
        (fresh, _agent_state(is_healthy=True), 1),
    ]

    out = await svc.select_nodes(preferred_region="fi")

    assert out == [fresh]
