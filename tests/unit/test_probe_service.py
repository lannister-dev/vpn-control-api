from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def _patch_enqueue():
    with patch("services.probe.drain_service.enqueue_pool_snapshots_for_backend", new=AsyncMock()):
        yield

from services.probe.drain_service import ProbeDrainService
from services.probe.ingestion_service import ProbeIngestionService
from services.probe.schemas import (
    ProbeAutoDrainMigrateIn,
    ProbeDrainMigrateIn,
    ProbeDrainMigrateOut,
    ProbeReportIn,
    ProbeSyntheticClientIds,
)


def _node(
        *,
        role: str = "backend",
        name: str = "node",
        region: str = "fi",
        public_domain: str = "prod.lannister-dev.ru",
        reality_ip: str = "203.0.113.10",
):
    n = MagicMock()
    n.id = uuid4()
    n.name = name
    n.region = region
    n.public_domain = public_domain
    n.reality_ip = reality_ip
    n.role = role
    n.is_active = True
    n.is_enabled = True
    n.is_draining = False
    return n


def _probe(*, is_reachable: bool, checked_at: datetime, route_id=None):
    p = MagicMock()
    p.id = uuid4()
    p.route_id = route_id
    p.is_reachable = is_reachable
    p.checked_at = checked_at
    return p


def _route(
        *,
        node_id=None,
        transport_profile_id=None,
        name: str = "route-fi-1",
        health_status: str = "healthy",
        base_weight: int = 50,
        cooldown_until: datetime | None = None,
):
    r = MagicMock()
    r.id = uuid4()
    r.name = name
    r.node_id = node_id or uuid4()
    r.transport_profile_id = transport_profile_id or uuid4()
    r.is_active = True
    r.health_status = health_status
    r.base_weight = base_weight
    r.cooldown_until = cooldown_until
    return r


def _transport_profile(
        *,
        name: str = "reality-main",
        network: str = "tcp",
        security: str = "reality",
        port: int = 443,
):
    tp = MagicMock()
    tp.id = uuid4()
    tp.name = name
    tp.network = network
    tp.security = security
    tp.port = port
    tp.flow = "xtls-rprx-vision"
    tp.reality_public_key = "pubkey"
    tp.reality_short_id = "0123456789abcdef"
    tp.reality_server_name = "reality.example.com"
    tp.tls_fingerprint = "chrome"
    return tp


def _ingestion_service() -> ProbeIngestionService:
    policy_repo = AsyncMock()
    policy_repo.get_current = AsyncMock(return_value=SimpleNamespace(
        auto_route_health_enabled=True,
        retention_days=30,
        route_suspected_after_failures=2,
        route_degraded_after_failures=3,
        route_block_after_failures=4,
        route_block_cooldown_hours=6,
    ))
    service = ProbeIngestionService(
        node_repository=AsyncMock(),
        probe_repository=AsyncMock(),
        route_repository=AsyncMock(),
        placement_repository=AsyncMock(),
        placement_transport=AsyncMock(),
        key_repository=AsyncMock(),
        alert_service=AsyncMock(),
        policy_repository=policy_repo,
        target_port=443,
        edge_public_domain="",
        synthetic_probe_client_ids=ProbeSyntheticClientIds(),
    )
    service.node_repository.list_public.return_value = []
    service.probe_repository.count_consecutive_route_failures = AsyncMock(return_value=1)
    return service


def _drain_service() -> ProbeDrainService:
    return ProbeDrainService(
        node_repository=AsyncMock(),
        probe_repository=AsyncMock(),
        placement_service=AsyncMock(),
        node_state_repository=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_report_rejects_unknown_node(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.node_repository.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await svc.report(
            ProbeReportIn(
                node_id=uuid4(),
                source="ru-probe-1",
                is_reachable=False,
                error="timeout",
            )
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_targets_filters_nodes(async_session):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()

    backend_ok = _node(role="backend", name="be-fi-1", region="fi", public_domain="be-fi.example.com")
    profile_ok = _transport_profile()
    route_ok = _route(node_id=backend_ok.id, transport_profile_id=profile_ok.id, name="route-reality-fi")
    backend_draining = _node(role="backend", name="be-fi-2", region="fi", public_domain="be-fi-2.example.com")
    backend_draining.is_draining = True
    profile_draining = _transport_profile()
    route_draining = _route(node_id=backend_draining.id, transport_profile_id=profile_draining.id, name="route-reality-drain")
    backend_disabled = _node(role="backend", name="be-nl-1", region="nl", public_domain="be-nl.example.com")
    backend_disabled.is_enabled = False
    profile_disabled = _transport_profile()
    route_disabled = _route(node_id=backend_disabled.id, transport_profile_id=profile_disabled.id, name="route-reality-disabled")
    backend_no_domain = _node(role="backend", name="be-empty", region="fi", public_domain="", reality_ip="")
    profile_no_domain = _transport_profile()
    route_no_domain = _route(node_id=backend_no_domain.id, transport_profile_id=profile_no_domain.id, name="route-no-host")
    svc.route_repository.list_active_detailed.return_value = [
        (route_ok, backend_ok, profile_ok, None),
        (route_draining, backend_draining, profile_draining, None),
        (route_disabled, backend_disabled, profile_disabled, None),
        (route_no_domain, backend_no_domain, profile_no_domain, None),
    ]

    out = await svc.list_targets()

    node_ids = {t.node_id for t in out}
    assert node_ids == {backend_ok.id, backend_draining.id}
    by_node = {t.node_id: t for t in out}
    ok_target = by_node[backend_ok.id]
    assert ok_target.route_id == route_ok.id
    assert ok_target.transport_kind == "reality"
    assert ok_target.target_host == backend_ok.reality_ip
    assert ok_target.target_port == 443
    assert ok_target.probe_client_id is None
    svc.route_repository.list_active_detailed.assert_awaited_once_with(limit=5000)

    out_no_drain = await svc.list_targets(include_draining=False)
    assert {t.node_id for t in out_no_drain} == {backend_ok.id}


@pytest.mark.asyncio
async def test_list_targets_skips_ws_routes_behind_shared_edge(async_session):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()
    svc.edge_public_domain = "edge.example.com"

    node = _node(public_domain="backend.example.com")
    transport_profile = _transport_profile(name="ws-main", network="ws", security="tls")
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id, name="route-ws")
    svc.route_repository.list_active_detailed.return_value = [(route, node, transport_profile, None)]

    out = await svc.list_targets()

    assert out == []


@pytest.mark.asyncio
async def test_list_targets_filters_by_node_role(async_session):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()

    backend_node = _node(role="backend", name="be-fi-1")
    backend_profile = _transport_profile()
    backend_route = _route(node_id=backend_node.id, transport_profile_id=backend_profile.id, name="route-backend")
    entry_node = _node(role="whitelist_entry", name="entry-fi-1")
    entry_profile = _transport_profile()
    entry_route = _route(node_id=entry_node.id, transport_profile_id=entry_profile.id, name="route-entry")
    svc.route_repository.list_active_detailed.return_value = [
        (backend_route, backend_node, backend_profile, None),
        (entry_route, entry_node, entry_profile, None),
    ]

    out = await svc.list_targets(role="backend")

    assert len(out) == 1
    assert out[0].node_id == backend_node.id
    assert out[0].route_id == backend_route.id


@pytest.mark.asyncio
async def test_list_targets_includes_tcp_targets_for_whitelist_entry_nodes(async_session):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()

    entry_node = _node(
        role="whitelist_entry",
        name="entry-fi-1",
        public_domain="entry.example.com",
        reality_ip="",
    )
    svc.route_repository.list_active_detailed.return_value = []
    svc.node_repository.list_public.return_value = [entry_node]

    out = await svc.list_targets(role="whitelist_entry")

    assert len(out) == 1
    assert out[0].node_id == entry_node.id
    assert out[0].route_id is None
    assert out[0].transport_profile_id is None
    assert out[0].transport_kind == "reality"
    assert out[0].probe_kind == "tcp_connect"
    assert out[0].target_host == "entry.example.com"
    assert out[0].target_port == 443


@pytest.mark.asyncio
async def test_list_targets_skips_disabled_whitelist_entry_nodes_by_default(async_session):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()

    entry_node = _node(
        role="whitelist_entry",
        name="entry-fi-1",
        public_domain="entry.example.com",
        reality_ip="",
    )
    entry_node.is_enabled = False
    svc.route_repository.list_active_detailed.return_value = []
    svc.node_repository.list_public.return_value = [entry_node]

    out = await svc.list_targets(role="whitelist_entry")

    assert out == []


@pytest.mark.asyncio
async def test_list_targets_includes_probe_client_id_when_special_key_is_synced(async_session):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.synthetic_probe_client_ids = ProbeSyntheticClientIds(reality="probe-reality-cid")

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id, name="route-reality")
    key = MagicMock()
    key.id = uuid4()
    key.client_id = "probe-reality-cid"
    key.transport = "reality"
    placement = MagicMock()
    placement.backend_node_id = node.id
    placement.applied_state = "applied"
    placement.op_version = 7
    placement.applied_version = 7

    svc.route_repository.list_active_detailed.return_value = [(route, node, transport_profile, None)]
    svc.key_repository.list_by_client_ids.return_value = [key]
    svc.placement_repository.list_by_key_id.return_value = [placement]

    out = await svc.list_targets()

    assert len(out) == 1
    assert out[0].probe_client_id == "probe-reality-cid"
    svc.key_repository.list_by_client_ids.assert_awaited_once_with(
        client_ids=["probe-reality-cid"],
        active_only=True,
    )
    svc.placement_repository.list_by_key_id.assert_awaited_once_with(
        key_id=key.id,
        active_only=True,
        desired_state="active",
    )


@pytest.mark.asyncio
async def test_list_targets_keeps_probe_client_id_when_special_key_is_pending(async_session):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.synthetic_probe_client_ids = ProbeSyntheticClientIds(reality="probe-reality-cid")

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id, name="route-reality")
    key = MagicMock()
    key.id = uuid4()
    key.client_id = "probe-reality-cid"
    key.transport = "reality"
    placement = MagicMock()
    placement.backend_node_id = node.id
    placement.applied_state = "pending"
    placement.op_version = 7
    placement.applied_version = 0

    svc.route_repository.list_active_detailed.return_value = [(route, node, transport_profile, None)]
    svc.key_repository.list_by_client_ids.return_value = [key]
    svc.placement_repository.list_by_key_id.return_value = [placement]

    out = await svc.list_targets()

    assert len(out) == 1
    assert out[0].probe_client_id == "probe-reality-cid"


def _entry_setup(role: str, *, configure_client: bool = True, extra_routes=True):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    if configure_client:
        svc.synthetic_probe_client_ids = ProbeSyntheticClientIds(reality="probe-reality-cid")

    entry = _node(role=role, name="entry-eu-1", public_domain="entry.example.com", reality_ip="")
    backend = _node(role="backend", name="backend-fi", public_domain="fi.example.com", reality_ip="1.2.3.4")
    tp = _transport_profile()
    entry_route = _route(node_id=backend.id, transport_profile_id=tp.id, name="entry→fi·reality")
    entry_route.entry_node_id = entry.id

    rows = [(entry_route, backend, tp, None)]
    if extra_routes:
        direct_route = _route(node_id=backend.id, transport_profile_id=tp.id, name="direct-fi·reality")
        direct_route.entry_node_id = None
        rows.append((direct_route, backend, tp, None))

    key = MagicMock()
    key.id = uuid4()
    key.client_id = "probe-reality-cid"
    key.transport = "reality"
    placement = MagicMock()
    placement.backend_node_id = backend.id
    placement.applied_state = "applied"
    placement.op_version = 1
    placement.applied_version = 1

    svc.route_repository.list_active_detailed.return_value = rows
    svc.key_repository.list_by_client_ids.return_value = [key]
    svc.placement_repository.list_by_key_id.return_value = [placement]
    svc.node_repository.list_public.return_value = [entry, backend]
    return svc, entry, backend, tp


@pytest.mark.asyncio
async def test_list_targets_emits_synthetic_for_entry_pool(async_session):
    svc, entry, backend, tp = _entry_setup(role="entry")
    out = await svc.list_targets(role="all")
    synth = [t for t in out if t.probe_kind == "synthetic_vpn" and t.node_id == entry.id]
    assert len(synth) == 1
    target = synth[0]
    assert target.target_host == "entry.example.com"
    assert target.target_port == 443
    assert target.reality_public_key == tp.reality_public_key
    assert target.reality_short_id == tp.reality_short_id
    assert target.reality_server_name == tp.reality_server_name
    assert target.probe_client_id == "probe-reality-cid"
    assert target.transport_kind == "reality"
    assert target.route_id is None
    assert target.transport_profile_id is None


@pytest.mark.asyncio
async def test_list_targets_emits_synthetic_for_whitelist_entry(async_session):
    svc, entry, _, tp = _entry_setup(role="whitelist_entry")
    out = await svc.list_targets(role="whitelist_entry")
    synth = [t for t in out if t.probe_kind == "synthetic_vpn" and t.node_id == entry.id]
    assert len(synth) == 1
    assert synth[0].reality_server_name == tp.reality_server_name


@pytest.mark.asyncio
async def test_list_targets_skips_entry_synthetic_without_configured_client(async_session):
    svc, entry, _, _ = _entry_setup(role="entry", configure_client=False)
    out = await svc.list_targets(role="all")
    synth = [t for t in out if t.probe_kind == "synthetic_vpn" and t.node_id == entry.id]
    assert synth == []
    tcp = [t for t in out if t.probe_kind == "tcp_connect" and t.node_id == entry.id]
    assert len(tcp) == 1


@pytest.mark.asyncio
async def test_list_targets_returns_all_active_routes_independently(async_session):
    svc = _ingestion_service()
    svc.route_repository = AsyncMock()

    backend = _node(role="backend", name="backend-fi")
    entry_a = _node(role="whitelist_entry", name="wl")
    entry_b = _node(role="entry", name="pool-entry")
    tp = _transport_profile()

    direct = _route(node_id=backend.id, transport_profile_id=tp.id, name="direct")
    direct.entry_node_id = None
    via_wl = _route(node_id=backend.id, transport_profile_id=tp.id, name="wl-suck-rkn")
    via_wl.entry_node_id = entry_a.id
    via_pool = _route(node_id=backend.id, transport_profile_id=tp.id, name="via-pool")
    via_pool.entry_node_id = entry_b.id

    svc.route_repository.list_active_detailed.return_value = [
        (via_wl, backend, tp, None),
        (via_pool, backend, tp, None),
        (direct, backend, tp, None),
    ]
    svc.node_repository.list_public.return_value = [backend]

    out = await svc.list_targets(role="backend")
    direct_probes = [t for t in out if t.node_id == backend.id]
    names = {t.route_name for t in direct_probes}
    assert names == {"direct", "wl-suck-rkn", "via-pool"}


@pytest.mark.asyncio
async def test_list_targets_includes_entry_synthetic_for_draining_backend(async_session):
    svc, _, backend, _ = _entry_setup(role="entry")
    backend.is_draining = True
    out = await svc.list_targets(role="all")
    synth = [t for t in out if t.probe_kind == "synthetic_vpn"]
    assert len(synth) >= 1
    synth_skip = await svc.list_targets(role="all", include_draining=False)
    assert [t for t in synth_skip if t.probe_kind == "synthetic_vpn"] == []


@pytest.mark.asyncio
async def test_report_success(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id)
    created = MagicMock()
    created.id = uuid4()
    created.node_id = node.id
    created.route_id = route.id
    created.transport_profile_id = transport_profile.id
    created.transport_kind = "reality"
    created.probe_kind = "synthetic_vpn"
    created.target_host = node.reality_ip
    created.target_port = 443
    created.error_phase = "tcp"
    created.source = "ru-probe-1"
    created.is_reachable = False
    created.latency_ms = None
    created.error = "timeout"
    created.checked_at = datetime.now(timezone.utc)
    created.details = {"asn": "12345"}
    created.created_at = datetime.now(timezone.utc)

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.create.return_value = created
    svc.probe_repository.get_latest_for_route.side_effect = [None, created]
    svc.probe_repository.count_consecutive_route_failures = AsyncMock(return_value=1)
    svc.route_repository.get_by_id.return_value = route

    out = await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=False,
            error="timeout",
            error_phase="tcp",
            details={"asn": "12345"},
        )
    )
    assert out.node_id == node.id
    assert out.route_id == route.id
    assert out.is_reachable is False
    svc.probe_repository.create.assert_awaited_once()
    svc.probe_repository.delete_older_than.assert_not_awaited()
    svc.alert_service.send_probe_status_change.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_blocks_routes_on_latest_failure(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id)
    checked_at = datetime.now(timezone.utc)
    created = _probe(is_reachable=False, checked_at=checked_at, route_id=route.id)
    created.node_id = node.id
    created.transport_profile_id = transport_profile.id
    created.transport_kind = "reality"
    created.probe_kind = "synthetic_vpn"
    created.target_host = node.reality_ip
    created.target_port = 443
    created.error_phase = "tcp"
    created.source = "ru-probe-1"
    created.latency_ms = None
    created.error = "timeout"
    created.details = {}
    created.created_at = datetime.now(timezone.utc)
    route.health_status = "healthy"
    route.base_weight = 50

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.get_latest_for_route.side_effect = [None, created]
    svc.probe_repository.create.return_value = created
    svc.probe_repository.count_consecutive_route_failures = AsyncMock(return_value=4)
    svc.route_repository.get_by_id.return_value = route
    svc.route_repository.update_by_id = AsyncMock(return_value=route)

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=False,
            error="timeout",
        )
    )

    svc.route_repository.update_by_id.assert_awaited_once()
    kwargs = svc.route_repository.update_by_id.await_args.kwargs
    assert kwargs["item_id"] == route.id
    assert kwargs["data"]["health_status"] == "blocked"
    assert kwargs["data"]["effective_weight"] == 0


@pytest.mark.asyncio
async def test_report_blocks_warming_up_route_on_repeated_failures(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id, health_status="warming_up")
    checked_at = datetime.now(timezone.utc)
    created = _probe(is_reachable=False, checked_at=checked_at, route_id=route.id)
    created.node_id = node.id
    created.transport_profile_id = transport_profile.id
    created.transport_kind = "reality"
    created.probe_kind = "synthetic_vpn"
    created.target_host = node.reality_ip
    created.target_port = 443
    created.error_phase = "tunnel_http"
    created.source = "ru-probe-1"
    created.latency_ms = None
    created.error = "tls eof"
    created.details = {}
    created.created_at = datetime.now(timezone.utc)
    route.base_weight = 50

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.get_latest_for_route.side_effect = [None, created]
    svc.probe_repository.create.return_value = created
    svc.probe_repository.count_consecutive_route_failures = AsyncMock(return_value=5)
    svc.route_repository.get_by_id.return_value = route
    svc.route_repository.update_by_id = AsyncMock(return_value=route)

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=False,
            error="tls eof",
            error_phase="tunnel_http",
        )
    )

    svc.route_repository.update_by_id.assert_awaited_once()
    kwargs = svc.route_repository.update_by_id.await_args.kwargs
    assert kwargs["item_id"] == route.id
    assert kwargs["data"]["health_status"] == "blocked"
    assert kwargs["data"]["effective_weight"] == 0


@pytest.mark.asyncio
async def test_report_recovers_blocked_route_after_cooldown(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id)
    checked_at = datetime.now(timezone.utc)
    created = _probe(is_reachable=True, checked_at=checked_at, route_id=route.id)
    created.node_id = node.id
    created.transport_profile_id = transport_profile.id
    created.transport_kind = "reality"
    created.probe_kind = "synthetic_vpn"
    created.target_host = node.reality_ip
    created.target_port = 443
    created.error_phase = None
    created.source = "ru-probe-1"
    created.latency_ms = 40
    created.error = None
    created.details = {}
    created.created_at = datetime.now(timezone.utc)
    route.health_status = "blocked"
    route.base_weight = 50
    route.cooldown_until = checked_at - timedelta(seconds=1)

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.get_latest_for_route.side_effect = [
        _probe(is_reachable=False, checked_at=checked_at, route_id=route.id),
        created,
    ]
    svc.probe_repository.create.return_value = created
    svc.route_repository.get_by_id.return_value = route
    svc.route_repository.update_by_id = AsyncMock(return_value=route)

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=True,
            latency_ms=40,
        )
    )

    svc.route_repository.update_by_id.assert_awaited_once()
    kwargs = svc.route_repository.update_by_id.await_args.kwargs
    assert kwargs["item_id"] == route.id
    assert kwargs["data"]["health_status"] == "warming_up"
    assert kwargs["data"]["effective_weight"] == 10
    assert kwargs["data"]["warmup_stage"] == 0


@pytest.mark.asyncio
async def test_report_node_level_signal_does_not_block_all_routes(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    created = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc))
    created.node_id = node.id
    created.transport_profile_id = None
    created.transport_kind = None
    created.probe_kind = "tcp_connect"
    created.target_host = node.public_domain
    created.target_port = 443
    created.error_phase = "tcp"
    created.source = "ru-probe-1"
    created.latency_ms = None
    created.error = "timeout"
    created.details = {}
    created.created_at = datetime.now(timezone.utc)

    svc.node_repository.get_by_id.return_value = node
    svc.probe_repository.get_latest_for_node.side_effect = [None, created]
    svc.probe_repository.create.return_value = created
    svc.route_repository.update_by_id = AsyncMock()

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            source="ru-probe-1",
            is_reachable=False,
            error="timeout",
        )
    )

    svc.route_repository.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_skips_side_effects_for_stale_signal(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id)
    stale_row = _probe(
        is_reachable=False,
        checked_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        route_id=route.id,
    )
    stale_row.node_id = node.id
    stale_row.transport_profile_id = transport_profile.id
    stale_row.transport_kind = "reality"
    stale_row.probe_kind = "synthetic_vpn"
    stale_row.target_host = node.reality_ip
    stale_row.target_port = 443
    stale_row.error_phase = "tcp"
    stale_row.source = "ru-probe-1"
    stale_row.latency_ms = None
    stale_row.error = "timeout"
    stale_row.details = {}
    stale_row.created_at = datetime.now(timezone.utc)
    latest_row = _probe(is_reachable=True, checked_at=datetime.now(timezone.utc), route_id=route.id)
    latest_row.node_id = node.id
    latest_row.source = "ru-probe-1"

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.get_latest_for_route.side_effect = [latest_row, latest_row]
    svc.probe_repository.create.return_value = stale_row
    svc.route_repository.get_by_id.return_value = route
    svc.route_repository.update_by_id = AsyncMock()

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=False,
            error="timeout",
            checked_at=stale_row.checked_at,
        )
    )

    svc.alert_service.send_probe_status_change.assert_not_awaited()
    svc.route_repository.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_alert_sent_on_recovery_transition(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id)
    previous = _probe(
        is_reachable=False,
        checked_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        route_id=route.id,
    )

    created = MagicMock()
    created.id = uuid4()
    created.node_id = node.id
    created.route_id = route.id
    created.transport_profile_id = transport_profile.id
    created.transport_kind = "reality"
    created.probe_kind = "synthetic_vpn"
    created.target_host = node.reality_ip
    created.target_port = 443
    created.error_phase = None
    created.source = "ru-probe-1"
    created.is_reachable = True
    created.latency_ms = 40
    created.error = None
    created.checked_at = datetime.now(timezone.utc)
    created.details = {}
    created.created_at = datetime.now(timezone.utc)

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.get_latest_for_route.side_effect = [previous, created]
    svc.probe_repository.create.return_value = created
    svc.route_repository.get_by_id.return_value = route

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=True,
            latency_ms=40,
        )
    )

    svc.alert_service.send_probe_status_change.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_alert_not_sent_without_status_transition(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id)
    previous = _probe(
        is_reachable=False,
        checked_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        route_id=route.id,
    )

    created = MagicMock()
    created.id = uuid4()
    created.node_id = node.id
    created.route_id = route.id
    created.transport_profile_id = transport_profile.id
    created.transport_kind = "reality"
    created.probe_kind = "synthetic_vpn"
    created.target_host = node.reality_ip
    created.target_port = 443
    created.error_phase = None
    created.source = "ru-probe-1"
    created.is_reachable = False
    created.latency_ms = None
    created.error = "timeout"
    created.checked_at = datetime.now(timezone.utc)
    created.details = {}
    created.created_at = datetime.now(timezone.utc)

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.get_latest_for_route.side_effect = [previous, created]
    svc.probe_repository.create.return_value = created
    svc.probe_repository.count_consecutive_route_failures = AsyncMock(return_value=1)
    svc.route_repository.get_by_id.return_value = route

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=False,
            error="timeout",
        )
    )

    svc.alert_service.send_probe_status_change.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_requeues_backend_inventory_after_consecutive_synthetic_failures(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.placement_transport = AsyncMock()
    svc.alert_service = AsyncMock()
    svc.synthetic_probe_client_ids = ProbeSyntheticClientIds(reality="probe-reality-cid")

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id)
    created = _probe(
        is_reachable=False,
        checked_at=datetime.now(timezone.utc),
        route_id=route.id,
    )
    created.node_id = node.id
    created.transport_profile_id = transport_profile.id
    created.transport_kind = "reality"
    created.probe_kind = "synthetic_vpn"
    created.target_host = node.reality_ip
    created.target_port = 443
    created.error_phase = "tunnel_http"
    created.source = "ru-probe-1"
    created.latency_ms = None
    created.error = "tls eof"
    created.details = {}
    created.created_at = datetime.now(timezone.utc)

    key = MagicMock()
    key.id = uuid4()
    key.client_id = "probe-reality-cid"
    key.transport = "reality"

    placement = MagicMock()
    placement.id = uuid4()
    placement.backend_node_id = node.id
    placement.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    placement.last_migration_reason = None
    placement.sticky_until = None

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.get_latest_for_route.side_effect = [None, created]
    svc.probe_repository.create.return_value = created
    svc.probe_repository.count_consecutive_route_failures = AsyncMock(return_value=3)
    svc.route_repository.get_by_id.return_value = route
    svc.key_repository.list_by_client_ids.return_value = [key]
    svc.placement_repository.list_by_key_id.return_value = [placement]
    other_placement_id = uuid4()
    svc.placement_repository.set_pending_for_backend.return_value = [placement.id, other_placement_id]

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=False,
            error="tls eof",
            error_phase="tunnel_http",
        )
    )

    svc.placement_repository.set_pending_for_backend.assert_awaited_once()
    kwargs = svc.placement_repository.set_pending_for_backend.await_args.kwargs
    assert kwargs["backend_node_id"] == node.id
    assert kwargs["last_migration_reason"] == "probe_synthetic_self_heal"
    assert isinstance(kwargs["updated_at"], datetime)
    svc.placement_transport.enqueue_for_placement_ids.assert_awaited_once_with(
        [placement.id, other_placement_id]
    )


@pytest.mark.asyncio
async def test_report_skips_synthetic_requeue_during_self_heal_cooldown(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.placement_transport = AsyncMock()
    svc.alert_service = AsyncMock()
    svc.synthetic_probe_client_ids = ProbeSyntheticClientIds(reality="probe-reality-cid")

    node = _node()
    transport_profile = _transport_profile()
    route = _route(node_id=node.id, transport_profile_id=transport_profile.id)
    created = _probe(
        is_reachable=False,
        checked_at=datetime.now(timezone.utc),
        route_id=route.id,
    )
    created.node_id = node.id
    created.transport_profile_id = transport_profile.id
    created.transport_kind = "reality"
    created.probe_kind = "synthetic_vpn"
    created.target_host = node.reality_ip
    created.target_port = 443
    created.error_phase = "tunnel_http"
    created.source = "ru-probe-1"
    created.latency_ms = None
    created.error = "tls eof"
    created.details = {}
    created.created_at = datetime.now(timezone.utc)

    key = MagicMock()
    key.id = uuid4()
    key.client_id = "probe-reality-cid"
    key.transport = "reality"

    placement = MagicMock()
    placement.id = uuid4()
    placement.backend_node_id = node.id
    placement.updated_at = datetime.now(timezone.utc)
    placement.last_migration_reason = "probe_synthetic_self_heal"
    placement.sticky_until = None

    svc.node_repository.get_by_id.return_value = node
    svc.route_repository.get_active_detailed_by_id.return_value = (route, node, transport_profile, None)
    svc.probe_repository.get_latest_for_route.side_effect = [None, created]
    svc.probe_repository.create.return_value = created
    svc.probe_repository.count_consecutive_route_failures = AsyncMock(return_value=3)
    svc.route_repository.get_by_id.return_value = route
    svc.key_repository.list_by_client_ids.return_value = [key]
    svc.placement_repository.list_by_key_id.return_value = [placement]

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            route_id=route.id,
            source="ru-probe-1",
            probe_kind="synthetic_vpn",
            is_reachable=False,
            error="tls eof",
            error_phase="tunnel_http",
        )
    )

    svc.placement_repository.set_pending_for_backend.assert_not_awaited()
    svc.placement_transport.enqueue_for_placement_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_old_signals_returns_deleted_count(async_session):
    svc = _ingestion_service()
    svc.probe_repository = AsyncMock()
    svc.probe_repository.delete_older_than.return_value = 7

    deleted = await svc.cleanup_old_signals()

    assert deleted == 7
    svc.probe_repository.delete_older_than.assert_awaited_once()


@pytest.mark.asyncio
async def test_drain_and_migrate_requires_recent_failure(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    source = _node(role="backend")
    svc.node_repository.get_by_id.return_value = source
    svc.probe_repository.get_latest_for_backend_node.return_value = None

    with pytest.raises(HTTPException) as exc:
        await svc.drain_and_migrate_backend(
            ProbeDrainMigrateIn(
                source_backend_id=source.id,
                require_recent_failure=True,
            )
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_drain_and_migrate_rejects_healthy_latest(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    source = _node(role="backend")
    latest = _probe(is_reachable=True, checked_at=datetime.now(timezone.utc))
    svc.node_repository.get_by_id.return_value = source
    svc.probe_repository.get_latest_for_backend_node.return_value = latest

    with pytest.raises(HTTPException) as exc:
        await svc.drain_and_migrate_backend(
            ProbeDrainMigrateIn(
                source_backend_id=source.id,
                require_recent_failure=True,
            )
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_drain_and_migrate_rejects_stale_failure(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    source = _node(role="backend")
    stale = datetime.now(timezone.utc) - timedelta(seconds=3600)
    latest = _probe(is_reachable=False, checked_at=stale)
    svc.node_repository.get_by_id.return_value = source
    svc.probe_repository.get_latest_for_backend_node.return_value = latest

    with pytest.raises(HTTPException) as exc:
        await svc.drain_and_migrate_backend(
            ProbeDrainMigrateIn(
                source_backend_id=source.id,
                require_recent_failure=True,
                max_probe_age_sec=120,
            )
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_drain_and_migrate_rejects_insufficient_consecutive_failures(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    source = _node(role="backend")
    latest = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc))
    older_fail = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc) - timedelta(seconds=20))
    older_ok = _probe(is_reachable=True, checked_at=datetime.now(timezone.utc) - timedelta(seconds=40))
    svc.node_repository.get_by_id.return_value = source
    svc.probe_repository.get_latest_for_backend_node.return_value = latest
    svc.probe_repository.list_recent_for_backend_node.return_value = [latest, older_fail, older_ok]

    with pytest.raises(HTTPException) as exc:
        await svc.drain_and_migrate_backend(
            ProbeDrainMigrateIn(
                source_backend_id=source.id,
                require_recent_failure=True,
                min_consecutive_failures=3,
            )
        )
    assert exc.value.status_code == 409
    assert "Insufficient consecutive probe failures" in exc.value.detail


@pytest.mark.asyncio
async def test_drain_and_migrate_success(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    source = _node(role="backend")
    latest = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc))
    migration = MagicMock()
    migration.source_backend_id = source.id
    migration.target_backend_id = uuid4()
    migration.migrated_count = 3

    svc.node_repository.get_by_id.return_value = source
    svc.probe_repository.get_latest_for_backend_node.return_value = latest
    svc.probe_repository.list_recent_for_backend_node.return_value = [latest]
    svc.placement_service.migrate_backend.return_value = migration
    svc.node_state_repository.get_one_by.return_value = SimpleNamespace(details={"heartbeat": {}})

    out = await svc.drain_and_migrate_backend(
        ProbeDrainMigrateIn(
            source_backend_id=source.id,
            require_recent_failure=True,
            min_consecutive_failures=1,
        )
    )

    assert out.source_backend_id == source.id
    assert out.target_backend_id == migration.target_backend_id
    assert out.migrated_count == 3
    assert out.drained is True
    assert out.probe_report_id == latest.id
    svc.node_repository.update_by_id.assert_awaited_once()
    svc.placement_service.migrate_backend.assert_awaited_once()
    svc.node_state_repository.update_by_node_id.assert_awaited_once()
    state_update = svc.node_state_repository.update_by_node_id.await_args.args[1]
    assert state_update["details"]["heartbeat"]["drain_reason"] == "probe_failure"


@pytest.mark.asyncio
async def test_auto_drain_and_migrate_backends_dry_run(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    backend_fail = _node(role="backend")
    backend_ok = _node(role="backend")
    backend_draining = _node(role="backend")
    backend_draining.is_draining = True
    extra_node = _node(role="gateway")
    svc.node_repository.list.return_value = [backend_fail, backend_ok, backend_draining, extra_node]

    fail_latest = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc))
    ok_latest = _probe(is_reachable=True, checked_at=datetime.now(timezone.utc))

    async def _latest_side_effect(*, node_id, source):
        if node_id == backend_fail.id:
            return fail_latest
        if node_id == backend_ok.id:
            return ok_latest
        return None

    svc.probe_repository.get_latest_for_backend_node.side_effect = _latest_side_effect

    out = await svc.auto_drain_and_migrate_backends(
        ProbeAutoDrainMigrateIn(
            source="ru-probe-1",
            dry_run=True,
            require_recent_failure=True,
        )
    )

    assert out.processed == 4
    assert out.migrated == 0
    assert out.skipped == 4
    assert any(i.action == "would_migrate" and i.source_backend_id == backend_fail.id for i in out.items)
    assert any(i.action == "skipped" and i.source_backend_id == backend_ok.id for i in out.items)
    assert any(i.action == "skipped" and i.source_backend_id == backend_draining.id for i in out.items)
    assert any(i.action == "skipped" and i.source_backend_id == extra_node.id for i in out.items)


@pytest.mark.asyncio
async def test_auto_drain_and_migrate_backends_executes(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    backend_fail = _node(role="backend")
    svc.node_repository.list.return_value = [backend_fail]
    fail_latest = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc))
    svc.probe_repository.get_latest_for_backend_node.return_value = fail_latest

    svc.drain_and_migrate_backend = AsyncMock(
        return_value=ProbeDrainMigrateOut(
            source_backend_id=backend_fail.id,
            target_backend_id=uuid4(),
            migrated_count=2,
            drained=True,
            probe_report_id=fail_latest.id,
        )
    )

    out = await svc.auto_drain_and_migrate_backends(
        ProbeAutoDrainMigrateIn(
            source="ru-probe-1",
            dry_run=False,
            require_recent_failure=True,
        )
    )

    assert out.processed == 1
    assert out.migrated == 1
    assert out.skipped == 0
    assert len(out.items) == 1
    assert out.items[0].action == "migrated"
    svc.drain_and_migrate_backend.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_drain_reverts_is_draining_on_migration_failure(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    backend_fail = _node(role="backend")
    svc.node_repository.list.return_value = [backend_fail]
    svc.node_repository.get_by_id.return_value = backend_fail
    fail_latest = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc))
    svc.probe_repository.get_latest_for_backend_node.return_value = fail_latest
    svc.placement_service.migrate_backend.side_effect = HTTPException(status_code=409, detail="No target backend available")

    out = await svc.auto_drain_and_migrate_backends(
        ProbeAutoDrainMigrateIn(
            source="ru-probe-1",
            dry_run=False,
            require_recent_failure=True,
        )
    )

    assert out.processed == 1
    assert out.migrated == 0
    assert out.skipped == 1
    assert out.items[0].action == "skipped"
    assert svc.node_repository.update_by_id.await_count == 2

    first_call = svc.node_repository.update_by_id.await_args_list[0]
    second_call = svc.node_repository.update_by_id.await_args_list[1]
    assert first_call.args[0] == backend_fail.id
    assert first_call.args[1]["is_draining"] is True
    assert second_call.args[0] == backend_fail.id
    assert second_call.args[1]["is_draining"] is False
