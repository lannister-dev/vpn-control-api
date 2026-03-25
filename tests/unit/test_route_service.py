from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.routes.schemas import (
    RouteCreateIn,
    RouteHealthAction,
    RouteHealthUpdateIn,
    RouteHealthStatus,
    RouteUpdateIn,
    TransportProfileCreateIn,
)
from services.routes.service import RouteService


def _node(*, role="backend", public_domain="node.example.com", reality_ip=None):
    n = MagicMock()
    n.id = uuid4()
    n.role = role
    n.public_domain = public_domain
    n.reality_ip = reality_ip
    n.upstream_node_id = None
    return n


def _mock_outbox(svc):
    svc.outbox_repository = AsyncMock()
    svc.outbox_repository.enqueue_many = AsyncMock()


def _transport_profile():
    t = MagicMock()
    t.id = uuid4()
    t.is_active = True
    return t


def _route(*, status="healthy", base_weight=50, effective_weight=50, cooldown_until=None, stage=None, started=None):
    r = MagicMock()
    r.id = uuid4()
    r.health_status = status
    r.base_weight = base_weight
    r.effective_weight = effective_weight
    r.cooldown_until = cooldown_until
    r.warmup_stage = stage
    r.warmup_started_at = started
    r.is_active = True
    r.name = "route-1"
    r.node_id = uuid4()
    r.entry_node_id = None
    r.transport_profile_id = uuid4()
    r.created_at = datetime.now(timezone.utc)
    r.updated_at = datetime.now(timezone.utc)
    return r


@pytest.mark.asyncio
async def test_create_route_accepts_backend_node(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.transport_repository = AsyncMock()
    svc.route_repository = AsyncMock()

    node = _node()
    node.role = "backend"
    svc.node_repository.get_by_id = AsyncMock(return_value=node)
    svc.transport_repository.get_by_id = AsyncMock(return_value=_transport_profile())
    svc.route_repository.get_one_by = AsyncMock(return_value=None)
    created = _route()
    created.node_id = node.id
    svc.route_repository.create = AsyncMock(return_value=created)

    payload = RouteCreateIn(
        name="be1-reality-google",
        node_id=node.id,
        transport_profile_id=uuid4(),
        base_weight=40,
        health_status=RouteHealthStatus.healthy,
    )

    out = await svc.create_route(payload)

    assert out.node_id == node.id


@pytest.mark.asyncio
async def test_create_route_rejects_non_backend_node(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.transport_repository = AsyncMock()
    svc.route_repository = AsyncMock()

    node = _node(role="whitelist_entry")
    svc.node_repository.get_by_id = AsyncMock(return_value=node)

    payload = RouteCreateIn(
        name="entry-as-backend",
        node_id=node.id,
        transport_profile_id=uuid4(),
        base_weight=40,
        health_status=RouteHealthStatus.healthy,
    )

    with pytest.raises(HTTPException) as exc:
        await svc.create_route(payload)

    assert exc.value.status_code == 422
    assert "role=backend" in exc.value.detail


@pytest.mark.asyncio
async def test_create_route_rejects_invalid_entry_node_role(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.transport_repository = AsyncMock()
    svc.route_repository = AsyncMock()

    backend = _node(role="backend")
    entry = _node(role="backend")
    svc.node_repository.get_by_id = AsyncMock(side_effect=[backend, entry])

    payload = RouteCreateIn(
        name="be1-reality-via-backend-entry",
        node_id=backend.id,
        entry_node_id=entry.id,
        transport_profile_id=uuid4(),
        base_weight=40,
        health_status=RouteHealthStatus.healthy,
    )

    with pytest.raises(HTTPException) as exc:
        await svc.create_route(payload)

    assert exc.value.status_code == 422
    assert "role=whitelist_entry" in exc.value.detail


@pytest.mark.asyncio
async def test_create_route_accepts_whitelist_entry_node(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.transport_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    _mock_outbox(svc)

    backend = _node(role="backend")
    entry = _node(role="whitelist_entry")
    # create_route: backend, entry; _sync_entry_upstream: entry (backend reused)
    svc.node_repository.get_by_id = AsyncMock(side_effect=[backend, entry, entry])
    svc.node_repository.update_by_id = AsyncMock(return_value=entry)
    svc.transport_repository.get_by_id = AsyncMock(return_value=_transport_profile())
    svc.route_repository.get_one_by = AsyncMock(return_value=None)
    created = _route()
    created.node_id = backend.id
    created.entry_node_id = entry.id
    svc.route_repository.create = AsyncMock(return_value=created)

    payload = RouteCreateIn(
        name="be1-reality-via-entry",
        node_id=backend.id,
        entry_node_id=entry.id,
        transport_profile_id=uuid4(),
        base_weight=40,
        health_status=RouteHealthStatus.healthy,
    )

    out = await svc.create_route(payload)

    assert out.node_id == backend.id
    assert out.entry_node_id == entry.id
    svc.outbox_repository.enqueue_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_transport_profile_conflict(async_session):
    svc = RouteService(async_session)
    svc.transport_repository = AsyncMock()

    existing = MagicMock()
    existing.is_active = True
    svc.transport_repository.get_one_by = AsyncMock(return_value=existing)

    payload = TransportProfileCreateIn(name="reality-vision-google")

    with pytest.raises(HTTPException) as exc:
        await svc.create_transport_profile(payload)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_transport_profile_rejects_invalid_reality_network(async_session):
    svc = RouteService(async_session)
    svc.transport_repository = AsyncMock()
    svc.transport_repository.get_one_by = AsyncMock(return_value=None)

    payload = TransportProfileCreateIn(
        name="bad-reality-ws",
        protocol="vless",
        network="ws",
        security="reality",
        reality_public_key="pk",
        reality_short_id="sid",
        reality_server_name="www.google.com",
    )

    with pytest.raises(HTTPException) as exc:
        await svc.create_transport_profile(payload)
    assert exc.value.status_code == 422
    assert "network=tcp" in exc.value.detail


@pytest.mark.asyncio
async def test_create_transport_profile_requires_reality_fields(async_session):
    svc = RouteService(async_session)
    svc.transport_repository = AsyncMock()
    svc.transport_repository.get_one_by = AsyncMock(return_value=None)

    payload = TransportProfileCreateIn(
        name="bad-reality-missing-fields",
        protocol="vless",
        network="tcp",
        security="reality",
    )

    with pytest.raises(HTTPException) as exc:
        await svc.create_transport_profile(payload)
    assert exc.value.status_code == 422
    assert "requires reality_public_key" in exc.value.detail


@pytest.mark.asyncio
async def test_create_transport_profile_rejects_reality_fields_for_tls(async_session):
    svc = RouteService(async_session)
    svc.transport_repository = AsyncMock()
    svc.transport_repository.get_one_by = AsyncMock(return_value=None)

    payload = TransportProfileCreateIn(
        name="bad-tls-with-reality-fields",
        protocol="vless",
        network="grpc",
        security="tls",
        reality_public_key="pk",
    )

    with pytest.raises(HTTPException) as exc:
        await svc.create_transport_profile(payload)
    assert exc.value.status_code == 422
    assert "does not support reality_* fields" in exc.value.detail


@pytest.mark.asyncio
async def test_create_transport_profile_defaults_grpc_service_name(async_session):
    svc = RouteService(async_session)
    svc.transport_repository = AsyncMock()
    svc.transport_repository.get_one_by = AsyncMock(return_value=None)
    created = MagicMock()
    created.id = uuid4()
    created.name = "grpc-profile"
    created.protocol = "vless"
    created.network = "grpc"
    created.security = "tls"
    created.flow = None
    created.reality_public_key = None
    created.reality_short_id = None
    created.reality_server_name = None
    created.tls_fingerprint = "chrome"
    created.grpc_service_name = "vl"
    created.port = 443
    created.is_active = True
    created.created_at = datetime.now(timezone.utc)
    created.updated_at = datetime.now(timezone.utc)
    svc.transport_repository.create = AsyncMock(return_value=created)

    payload = TransportProfileCreateIn(
        name="grpc-profile",
        protocol="vless",
        network="grpc",
        security="tls",
        tls_fingerprint="chrome",
        port=443,
    )

    out = await svc.create_transport_profile(payload)

    assert out.grpc_service_name == "vl"
    svc.transport_repository.create.assert_awaited_once()
    create_data = svc.transport_repository.create.await_args.args[0]
    assert create_data["protocol"] == "vless"
    assert create_data["network"] == "grpc"
    assert create_data["security"] == "tls"
    assert create_data["grpc_service_name"] == "vl"


@pytest.mark.asyncio
async def test_update_route_health_block_sets_cooldown(async_session):
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()

    route = _route(status="healthy", base_weight=40, effective_weight=40)
    svc.route_repository.get_by_id = AsyncMock(return_value=route)
    svc.route_repository.update_by_id = AsyncMock(return_value=route)

    await svc.update_route_health(
        route.id,
        RouteHealthUpdateIn(action=RouteHealthAction.block, cooldown_hours=6),
    )

    svc.route_repository.update_by_id.assert_awaited_once()
    kwargs = svc.route_repository.update_by_id.await_args.kwargs
    data = kwargs["data"]
    assert data["health_status"] == RouteHealthStatus.blocked.value
    assert data["effective_weight"] == 0
    assert data["cooldown_until"] is not None


@pytest.mark.asyncio
async def test_update_route_health_recover_rejects_active_cooldown(async_session):
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()

    route = _route(
        status="blocked",
        base_weight=40,
        effective_weight=0,
        cooldown_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    svc.route_repository.get_by_id = AsyncMock(return_value=route)

    with pytest.raises(HTTPException) as exc:
        await svc.update_route_health(
            route.id,
            RouteHealthUpdateIn(action=RouteHealthAction.recover, cooldown_hours=6),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_advance_warmup_progress_and_finalize(async_session):
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()

    old = datetime.now(timezone.utc) - timedelta(minutes=61)
    route_advance = _route(status="warming_up", base_weight=50, effective_weight=10, stage=0, started=old)
    route_finalize = _route(status="warming_up", base_weight=15, effective_weight=15, stage=1, started=old)
    svc.route_repository.list_warming_up = AsyncMock(return_value=[route_advance, route_finalize])
    svc.route_repository.update_by_id = AsyncMock(side_effect=[route_advance, route_finalize])

    out = await svc.advance_warmup()

    assert out.processed == 2
    assert out.advanced == 1
    assert out.finalized == 1
    assert svc.route_repository.update_by_id.await_count == 2


@pytest.mark.asyncio
async def test_list_routes_includes_routing_diagnostics(async_session):
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()

    healthy_route = _route(status="healthy", base_weight=50, effective_weight=50)
    blocked_route = _route(status="blocked", base_weight=50, effective_weight=0)

    healthy_node = MagicMock(
        id=healthy_route.node_id,
        is_active=True,
        is_enabled=True,
        is_draining=False,
    )
    unhealthy_node = MagicMock(
        id=blocked_route.node_id,
        is_active=True,
        is_enabled=True,
        is_draining=False,
    )
    transport = MagicMock(is_active=True)
    recent_state = MagicMock(
        is_healthy=True,
        last_seen_at=datetime.now(timezone.utc),
    )
    stale_state = MagicMock(
        is_healthy=True,
        last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    svc.route_repository.list_active_detailed = AsyncMock(
        return_value=[
            (healthy_route, healthy_node, transport, recent_state),
            (blocked_route, unhealthy_node, transport, stale_state),
        ]
    )

    out = await svc.list_routes(limit=10)

    assert len(out) == 2
    assert out[0].routing_eligible is True
    assert out[0].routing_reason is None
    assert out[1].routing_eligible is False
    assert out[1].routing_reason == "route_zero_weight"


@pytest.mark.asyncio
async def test_update_route_sets_entry_node(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    _mock_outbox(svc)

    entry = _node(role="whitelist_entry")
    backend = _node(role="backend")
    route = _route()
    route.entry_node_id = None
    route.node_id = backend.id
    svc.route_repository.get_by_id = AsyncMock(return_value=route)
    # update_route: entry (validate); _sync_entry_upstream: entry (check upstream), backend (not cached)
    svc.node_repository.get_by_id = AsyncMock(side_effect=[entry, entry, backend])
    svc.node_repository.update_by_id = AsyncMock(return_value=entry)

    updated_route = _route()
    updated_route.id = route.id
    updated_route.entry_node_id = entry.id
    svc.route_repository.update_by_id = AsyncMock(return_value=updated_route)

    payload = RouteUpdateIn(entry_node_id=entry.id)
    out = await svc.update_route(route.id, payload)

    svc.route_repository.update_by_id.assert_awaited_once()
    call_args = svc.route_repository.update_by_id.await_args
    call_data = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs["data"]
    assert call_data["entry_node_id"] == entry.id
    assert out.entry_node_id == entry.id


@pytest.mark.asyncio
async def test_update_route_detach_entry_node(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()

    route = _route()
    route.entry_node_id = uuid4()
    svc.route_repository.get_by_id = AsyncMock(return_value=route)

    updated_route = _route()
    updated_route.id = route.id
    updated_route.entry_node_id = None
    svc.route_repository.update_by_id = AsyncMock(return_value=updated_route)

    payload = RouteUpdateIn(entry_node_id=None)
    out = await svc.update_route(route.id, payload)

    svc.route_repository.update_by_id.assert_awaited_once()
    call_args = svc.route_repository.update_by_id.await_args
    call_data = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs["data"]
    assert call_data["entry_node_id"] is None
    assert out.entry_node_id is None


@pytest.mark.asyncio
async def test_update_route_rejects_non_entry_role(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()

    backend_node = _node(role="backend")
    route = _route()
    svc.route_repository.get_by_id = AsyncMock(return_value=route)
    svc.node_repository.get_by_id = AsyncMock(return_value=backend_node)

    payload = RouteUpdateIn(entry_node_id=backend_node.id)

    with pytest.raises(HTTPException) as exc:
        await svc.update_route(route.id, payload)

    assert exc.value.status_code == 422
    assert "role=whitelist_entry" in exc.value.detail


@pytest.mark.asyncio
async def test_update_route_noop_when_field_not_sent(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()

    route = _route()
    route.entry_node_id = None
    svc.route_repository.get_by_id = AsyncMock(return_value=route)

    payload = RouteUpdateIn()
    out = await svc.update_route(route.id, payload)

    svc.route_repository.update_by_id.assert_not_awaited()
    assert out.id == route.id


@pytest.mark.asyncio
async def test_update_route_not_found(async_session):
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id = AsyncMock(return_value=None)

    payload = RouteUpdateIn(entry_node_id=None)

    with pytest.raises(HTTPException) as exc:
        await svc.update_route(uuid4(), payload)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_route_changes_backend_node(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    _mock_outbox(svc)

    new_backend = _node(role="backend")
    route = _route()
    route.entry_node_id = None
    svc.route_repository.get_by_id = AsyncMock(return_value=route)
    svc.node_repository.get_by_id = AsyncMock(return_value=new_backend)

    updated_route = _route()
    updated_route.id = route.id
    updated_route.node_id = new_backend.id
    updated_route.entry_node_id = None
    svc.route_repository.update_by_id = AsyncMock(return_value=updated_route)

    payload = RouteUpdateIn(node_id=new_backend.id)
    out = await svc.update_route(route.id, payload)

    svc.route_repository.update_by_id.assert_awaited_once()
    call_data = svc.route_repository.update_by_id.await_args.args[1]
    assert call_data["node_id"] == new_backend.id
    assert out.node_id == new_backend.id


@pytest.mark.asyncio
async def test_update_route_rejects_non_backend_node_id(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()

    entry_node = _node(role="whitelist_entry")
    route = _route()
    svc.route_repository.get_by_id = AsyncMock(return_value=route)
    svc.node_repository.get_by_id = AsyncMock(return_value=entry_node)

    payload = RouteUpdateIn(node_id=entry_node.id)

    with pytest.raises(HTTPException) as exc:
        await svc.update_route(route.id, payload)

    assert exc.value.status_code == 422
    assert "role=backend" in exc.value.detail


@pytest.mark.asyncio
async def test_update_route_changes_name(async_session):
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()

    route = _route()
    svc.route_repository.get_by_id = AsyncMock(return_value=route)
    svc.route_repository.get_one_by = AsyncMock(return_value=None)

    updated_route = _route()
    updated_route.id = route.id
    updated_route.name = "new-name"
    svc.route_repository.update_by_id = AsyncMock(return_value=updated_route)

    payload = RouteUpdateIn(name="new-name")
    out = await svc.update_route(route.id, payload)

    svc.route_repository.update_by_id.assert_awaited_once()
    call_data = svc.route_repository.update_by_id.await_args.args[1]
    assert call_data["name"] == "new-name"
    assert out.name == "new-name"


@pytest.mark.asyncio
async def test_update_route_name_conflict(async_session):
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()

    route = _route()
    existing = _route()
    existing.name = "taken-name"
    existing.is_active = True
    svc.route_repository.get_by_id = AsyncMock(return_value=route)
    svc.route_repository.get_one_by = AsyncMock(return_value=existing)

    payload = RouteUpdateIn(name="taken-name")

    with pytest.raises(HTTPException) as exc:
        await svc.update_route(route.id, payload)

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_route_changes_base_weight(async_session):
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()

    route = _route(base_weight=50, effective_weight=50)
    svc.route_repository.get_by_id = AsyncMock(return_value=route)

    updated_route = _route(base_weight=80, effective_weight=80)
    updated_route.id = route.id
    svc.route_repository.update_by_id = AsyncMock(return_value=updated_route)

    payload = RouteUpdateIn(base_weight=80)
    out = await svc.update_route(route.id, payload)

    svc.route_repository.update_by_id.assert_awaited_once()
    call_data = svc.route_repository.update_by_id.await_args.args[1]
    assert call_data["base_weight"] == 80
    assert call_data["effective_weight"] == 80


@pytest.mark.asyncio
async def test_update_route_base_weight_keeps_lower_effective(async_session):
    """When effective_weight < base_weight (e.g. warming up), don't auto-bump effective."""
    svc = RouteService(async_session)
    svc.route_repository = AsyncMock()

    route = _route(base_weight=50, effective_weight=20)
    svc.route_repository.get_by_id = AsyncMock(return_value=route)

    updated_route = _route(base_weight=80, effective_weight=20)
    updated_route.id = route.id
    svc.route_repository.update_by_id = AsyncMock(return_value=updated_route)

    payload = RouteUpdateIn(base_weight=80)
    await svc.update_route(route.id, payload)

    call_data = svc.route_repository.update_by_id.await_args.args[1]
    assert call_data["base_weight"] == 80
    assert "effective_weight" not in call_data


@pytest.mark.asyncio
async def test_update_route_multiple_fields(async_session):
    svc = RouteService(async_session)
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    _mock_outbox(svc)

    new_backend = _node(role="backend")
    entry = _node(role="whitelist_entry")
    route = _route()
    route.entry_node_id = None
    svc.route_repository.get_by_id = AsyncMock(return_value=route)
    # update_route: new_backend, entry; _sync_entry_upstream: entry (backend reused)
    svc.node_repository.get_by_id = AsyncMock(side_effect=[new_backend, entry, entry])
    svc.node_repository.update_by_id = AsyncMock(return_value=entry)
    svc.route_repository.get_one_by = AsyncMock(return_value=None)

    updated_route = _route()
    updated_route.id = route.id
    updated_route.node_id = new_backend.id
    updated_route.entry_node_id = entry.id
    updated_route.name = "new-route-name"
    svc.route_repository.update_by_id = AsyncMock(return_value=updated_route)

    payload = RouteUpdateIn(name="new-route-name", node_id=new_backend.id, entry_node_id=entry.id)
    out = await svc.update_route(route.id, payload)

    call_data = svc.route_repository.update_by_id.await_args.args[1]
    assert call_data["name"] == "new-route-name"
    assert call_data["node_id"] == new_backend.id
    assert call_data["entry_node_id"] == entry.id
    assert out.node_id == new_backend.id
    assert out.entry_node_id == entry.id
