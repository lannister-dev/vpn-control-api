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


def _make_repo(*, available, traffic=None):
    repo = AsyncMock()
    repo.list_available_nodes.return_value = available
    repo.recent_traffic_bytes_per_backend.return_value = traffic or {}
    return repo


@pytest.mark.asyncio
async def test_select_nodes_filters_and_scores(async_session):
    svc = RoutingService(async_session)

    strong = _node(region="fi", capacity=100)
    weak = _node(region="fi", capacity=100)
    unhealthy = _node(region="fi", capacity=100)
    full = _node(region="fi", capacity=10)

    svc.repository = _make_repo(available=[
        (weak, _agent_state(is_healthy=True), 90),
        (strong, _agent_state(is_healthy=True), 10),
        (unhealthy, _agent_state(is_healthy=False), 5),
        (full, _agent_state(is_healthy=True), 10),
    ])

    out = await svc.select_nodes(preferred_region="fi")

    assert out == [strong, weak]
    svc.repository.list_available_nodes.assert_awaited_once_with(
        preferred_region="fi",
        exclude_node_ids=None,
    )


@pytest.mark.asyncio
async def test_select_nodes_returns_empty(async_session):
    svc = RoutingService(async_session)
    svc.repository = _make_repo(available=[])

    out = await svc.select_nodes()

    assert out == []


@pytest.mark.asyncio
async def test_select_nodes_skips_stale_last_seen(async_session):
    svc = RoutingService(async_session)
    svc.node_state_stale_after_sec = 90

    stale = _node(region="fi", capacity=100)
    fresh = _node(region="fi", capacity=100)
    svc.repository = _make_repo(available=[
        (
            stale,
            _agent_state(
                is_healthy=True,
                last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            ),
            1,
        ),
        (fresh, _agent_state(is_healthy=True), 1),
    ])

    out = await svc.select_nodes(preferred_region="fi")

    assert out == [fresh]


@pytest.mark.asyncio
async def test_select_nodes_demotes_traffic_heavy_backend(async_session):
    svc = RoutingService(async_session)

    quiet = _node(region="fi", capacity=100)
    busy = _node(region="fi", capacity=100)

    svc.repository = _make_repo(
        available=[
            (busy, _agent_state(is_healthy=True), 30),
            (quiet, _agent_state(is_healthy=True), 30),
        ],
        traffic={busy.id: 50_000_000_000, quiet.id: 1_000_000_000},
    )

    out = await svc.select_nodes(preferred_region="fi")

    assert out == [quiet, busy]


@pytest.mark.asyncio
async def test_select_nodes_traffic_outweighs_count_when_count_equal(async_session):
    svc = RoutingService(async_session)

    light_load_high_traffic = _node(region="fi", capacity=100)
    heavy_load_low_traffic = _node(region="fi", capacity=100)

    svc.repository = _make_repo(
        available=[
            (light_load_high_traffic, _agent_state(is_healthy=True), 5),
            (heavy_load_low_traffic, _agent_state(is_healthy=True), 70),
        ],
        traffic={
            light_load_high_traffic.id: 100_000_000_000,
            heavy_load_low_traffic.id: 100_000_000,
        },
    )

    out = await svc.select_nodes(preferred_region="fi")

    assert out == [heavy_load_low_traffic, light_load_high_traffic]


@pytest.mark.asyncio
async def test_select_nodes_falls_back_to_count_when_no_traffic_data(async_session):
    svc = RoutingService(async_session)

    less_loaded = _node(region="fi", capacity=100)
    more_loaded = _node(region="fi", capacity=100)

    svc.repository = _make_repo(
        available=[
            (more_loaded, _agent_state(is_healthy=True), 80),
            (less_loaded, _agent_state(is_healthy=True), 20),
        ],
        traffic={},
    )

    out = await svc.select_nodes(preferred_region="fi")

    assert out == [less_loaded, more_loaded]
