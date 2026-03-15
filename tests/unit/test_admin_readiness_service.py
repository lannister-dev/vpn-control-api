from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.admin_status.service import AdminStatusService


def _node(*, role: str, enabled: bool, draining: bool):
    n = MagicMock()
    n.id = uuid4()
    n.name = f"node-{n.id.hex[:6]}"
    n.role = role
    n.region = "fi"
    n.public_domain = "prod.example.com"
    n.is_active = True
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
async def test_admin_readiness_not_ready_when_basics_missing(async_session):
    svc = AdminStatusService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.profile_artifact_repository = AsyncMock()

    svc.node_repository.list_active_with_agent_state = AsyncMock(return_value=[])
    svc.route_repository.count_resolved_active = AsyncMock(return_value=0)
    svc.route_repository.count_resolved_active_by_region = AsyncMock(return_value={})
    svc.profile_artifact_repository.get_active = AsyncMock(return_value=None)

    out = await svc.get_readiness()

    assert out.ready is False
    by_name = {item.name: item for item in out.checks}
    assert by_name["active_profiles_artifact"].ok is False
    assert by_name["healthy_backend_nodes"].ok is False
    assert by_name["resolvable_active_routes"].ok is False
    assert by_name["healthy_regions_route_coverage"].ok is False


@pytest.mark.asyncio
async def test_admin_readiness_ready_when_all_checks_pass(async_session):
    svc = AdminStatusService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.profile_artifact_repository = AsyncMock()

    backend = _node(role="backend", enabled=True, draining=False)
    backend_state = _state(healthy=True)

    svc.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(backend, backend_state)]
    )
    svc.route_repository.count_resolved_active = AsyncMock(return_value=3)
    svc.route_repository.count_resolved_active_by_region = AsyncMock(return_value={"fi": 3})
    svc.profile_artifact_repository.get_active = AsyncMock(return_value=MagicMock())

    out = await svc.get_readiness()

    assert out.ready is True
    by_name = {item.name: item for item in out.checks}
    assert by_name["active_profiles_artifact"].ok is True
    assert by_name["healthy_backend_nodes"].ok is True
    assert by_name["resolvable_active_routes"].ok is True
    assert by_name["healthy_regions_route_coverage"].ok is True


@pytest.mark.asyncio
async def test_admin_readiness_excludes_stale_backend_from_healthy_regions(async_session):
    svc = AdminStatusService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.profile_artifact_repository = AsyncMock()

    backend = _node(role="backend", enabled=True, draining=False)
    backend_state = _state(healthy=True)
    backend_state.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    svc.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(backend, backend_state)]
    )
    svc.route_repository.count_resolved_active = AsyncMock(return_value=0)
    svc.route_repository.count_resolved_active_by_region = AsyncMock(return_value={})
    svc.profile_artifact_repository.get_active = AsyncMock(return_value=MagicMock())

    out = await svc.get_readiness()

    by_name = {item.name: item for item in out.checks}
    assert by_name["healthy_backend_nodes"].ok is False
    assert by_name["healthy_regions_route_coverage"].ok is False
