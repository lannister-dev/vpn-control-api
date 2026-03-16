from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.admin_status.service import AdminStatusService


def _node(*, enabled: bool, draining: bool):
    n = MagicMock()
    n.id = uuid4()
    n.name = f"node-{n.id.hex[:6]}"
    n.region = "fi"
    n.public_domain = "prod.example.com"
    n.is_enabled = enabled
    n.is_draining = draining
    n.capacity = 100
    return n


def _state(*, healthy: bool):
    s = MagicMock()
    s.is_healthy = healthy
    s.last_seen_at = datetime.now(timezone.utc)
    s.last_sync_at = datetime.now(timezone.utc)
    return s


@pytest.mark.asyncio
async def test_admin_status_empty(async_session):
    svc = AdminStatusService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.node_repository.list_active_with_agent_state = AsyncMock(return_value=[])
    svc.placement_repository.count_active_by_backend_node = AsyncMock(return_value={})

    out = await svc.get_status()

    assert out.totals.nodes_total == 0
    assert out.totals.nodes_enabled == 0
    assert out.totals.nodes_draining == 0
    assert out.totals.nodes_healthy == 0
    assert out.totals.placements_total == 0
    assert out.nodes == []


@pytest.mark.asyncio
async def test_admin_status_aggregates(async_session):
    svc = AdminStatusService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    primary = _node(enabled=True, draining=False)
    secondary = _node(enabled=False, draining=True)
    primary.reality_ip = "203.0.113.7"
    primary_state = _state(healthy=True)
    secondary_state = _state(healthy=False)

    svc.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(primary, primary_state), (secondary, secondary_state)]
    )
    svc.placement_repository.count_active_by_backend_node = AsyncMock(
        return_value={primary.id: 3}
    )

    out = await svc.get_status()

    assert out.totals.nodes_total == 2
    assert out.totals.nodes_enabled == 1
    assert out.totals.nodes_draining == 1
    assert out.totals.nodes_healthy == 1
    assert out.totals.placements_total == 3
    assert len(out.nodes) == 2
    by_id = {item.id: item for item in out.nodes}
    assert by_id[primary.id].placements_backend == 3
    assert by_id[primary.id].reality_ip == "203.0.113.7"
    assert by_id[primary.id].routing_eligible is True
    assert by_id[primary.id].routing_reason is None
    assert by_id[secondary.id].reality_ip is None
    assert by_id[secondary.id].routing_eligible is False
    assert by_id[secondary.id].routing_reason == "node_disabled"


@pytest.mark.asyncio
async def test_admin_status_marks_stale_node_unhealthy(async_session):
    svc = AdminStatusService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    node = _node(enabled=True, draining=False)
    stale_state = _state(healthy=True)
    stale_state.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    svc.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(node, stale_state)]
    )
    svc.placement_repository.count_active_by_backend_node = AsyncMock(
        return_value={node.id: 1}
    )

    out = await svc.get_status()

    assert out.totals.nodes_healthy == 0
    assert out.nodes[0].is_healthy is False
    assert out.nodes[0].routing_eligible is False
    assert out.nodes[0].routing_reason == "heartbeat_stale"
