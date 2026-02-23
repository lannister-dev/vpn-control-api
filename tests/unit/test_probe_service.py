from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.probe.drain_service import ProbeDrainService
from services.probe.ingestion_service import ProbeIngestionService
from services.probe.schemas import ProbeAutoDrainMigrateIn, ProbeDrainMigrateIn, ProbeDrainMigrateOut, ProbeReportIn


def _node(
        *,
        role: str = "backend",
        name: str = "node",
        region: str = "fi",
        public_domain: str = "prod.lannister-dev.ru",
):
    n = MagicMock()
    n.id = uuid4()
    n.name = name
    n.region = region
    n.public_domain = public_domain
    n.role = role
    n.is_active = True
    n.is_enabled = True
    n.is_draining = False
    return n


def _probe(*, is_reachable: bool, checked_at: datetime):
    p = MagicMock()
    p.id = uuid4()
    p.is_reachable = is_reachable
    p.checked_at = checked_at
    return p


def _route(
        *,
        health_status: str = "healthy",
        base_weight: int = 50,
        cooldown_until: datetime | None = None,
):
    r = MagicMock()
    r.id = uuid4()
    r.health_status = health_status
    r.base_weight = base_weight
    r.cooldown_until = cooldown_until
    return r


def _ingestion_service() -> ProbeIngestionService:
    return ProbeIngestionService(
        node_repository=AsyncMock(),
        probe_repository=AsyncMock(),
        route_repository=AsyncMock(),
        alert_service=AsyncMock(),
        target_port=443,
        retention_days=30,
        auto_route_health_enabled=True,
        route_block_cooldown_hours=6,
    )


def _drain_service() -> ProbeDrainService:
    return ProbeDrainService(
        node_repository=AsyncMock(),
        probe_repository=AsyncMock(),
        placement_service=AsyncMock(),
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
    svc.node_repository = AsyncMock()

    backend_ok = _node(role="backend", name="be-fi-1", region="fi", public_domain="be-fi.example.com")
    backend_draining = _node(role="backend", name="be-fi-2", region="fi", public_domain="be-fi-2.example.com")
    backend_draining.is_draining = True
    backend_disabled = _node(role="backend", name="be-nl-1", region="nl", public_domain="be-nl.example.com")
    backend_disabled.is_enabled = False
    backend_no_domain = _node(role="backend", name="be-empty", region="fi", public_domain="")
    svc.node_repository.list_public.return_value = [
        backend_ok,
        backend_draining,
        backend_disabled,
        backend_no_domain,
    ]

    out = await svc.list_targets()

    assert len(out) == 1
    assert out[0].node_id == backend_ok.id
    assert out[0].host == "be-fi.example.com"
    assert out[0].port == 443
    svc.node_repository.list_public.assert_awaited_once_with(role="backend")


@pytest.mark.asyncio
async def test_report_success(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    created = MagicMock()
    created.id = uuid4()
    created.node_id = node.id
    created.source = "ru-probe-1"
    created.is_reachable = False
    created.latency_ms = None
    created.error = "timeout"
    created.checked_at = datetime.now(timezone.utc)
    created.details = {"asn": "12345"}
    created.created_at = datetime.now(timezone.utc)

    svc.node_repository.get_by_id.return_value = node
    svc.probe_repository.get_latest_for_node.return_value = None
    svc.probe_repository.create.return_value = created
    svc.probe_repository.get_latest_for_node.side_effect = [None, created]
    svc.route_repository.list_active.return_value = []

    out = await svc.report(
        ProbeReportIn(
            node_id=node.id,
            source="ru-probe-1",
            is_reachable=False,
            error="timeout",
            details={"asn": "12345"},
        )
    )
    assert out.node_id == node.id
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
    checked_at = datetime.now(timezone.utc)
    created = _probe(is_reachable=False, checked_at=checked_at)
    created.node_id = node.id
    created.source = "ru-probe-1"
    created.latency_ms = None
    created.error = "timeout"
    created.details = {}
    created.created_at = datetime.now(timezone.utc)
    route = _route(health_status="healthy", base_weight=50)

    svc.node_repository.get_by_id.return_value = node
    svc.probe_repository.get_latest_for_node.side_effect = [None, created]
    svc.probe_repository.create.return_value = created
    svc.route_repository.list_active.return_value = [route]
    svc.route_repository.update_by_id = AsyncMock(return_value=route)

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            source="ru-probe-1",
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
async def test_report_recovers_blocked_route_after_cooldown(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    checked_at = datetime.now(timezone.utc)
    created = _probe(is_reachable=True, checked_at=checked_at)
    created.node_id = node.id
    created.source = "ru-probe-1"
    created.latency_ms = 40
    created.error = None
    created.details = {}
    created.created_at = datetime.now(timezone.utc)
    route = _route(
        health_status="blocked",
        base_weight=50,
        cooldown_until=checked_at - timedelta(seconds=1),
    )

    svc.node_repository.get_by_id.return_value = node
    svc.probe_repository.get_latest_for_node.side_effect = [_probe(is_reachable=False, checked_at=checked_at), created]
    svc.probe_repository.create.return_value = created
    svc.route_repository.list_active.return_value = [route]
    svc.route_repository.update_by_id = AsyncMock(return_value=route)

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            source="ru-probe-1",
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
async def test_report_skips_side_effects_for_stale_signal(async_session):
    svc = _ingestion_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.alert_service = AsyncMock()

    node = _node()
    stale_row = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    stale_row.node_id = node.id
    stale_row.source = "ru-probe-1"
    stale_row.latency_ms = None
    stale_row.error = "timeout"
    stale_row.details = {}
    stale_row.created_at = datetime.now(timezone.utc)
    latest_row = _probe(is_reachable=True, checked_at=datetime.now(timezone.utc))
    latest_row.node_id = node.id
    latest_row.source = "ru-probe-1"

    svc.node_repository.get_by_id.return_value = node
    svc.probe_repository.get_latest_for_node.side_effect = [latest_row, latest_row]
    svc.probe_repository.create.return_value = stale_row
    svc.route_repository.list_active.return_value = [_route()]
    svc.route_repository.update_by_id = AsyncMock()

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            source="ru-probe-1",
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
    previous = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc) - timedelta(seconds=30))

    created = MagicMock()
    created.id = uuid4()
    created.node_id = node.id
    created.source = "ru-probe-1"
    created.is_reachable = True
    created.latency_ms = 40
    created.error = None
    created.checked_at = datetime.now(timezone.utc)
    created.details = {}
    created.created_at = datetime.now(timezone.utc)

    svc.node_repository.get_by_id.return_value = node
    svc.probe_repository.get_latest_for_node.side_effect = [previous, created]
    svc.probe_repository.create.return_value = created
    svc.route_repository.list_active.return_value = []

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            source="ru-probe-1",
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
    previous = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc) - timedelta(seconds=30))

    created = MagicMock()
    created.id = uuid4()
    created.node_id = node.id
    created.source = "ru-probe-1"
    created.is_reachable = False
    created.latency_ms = None
    created.error = "timeout"
    created.checked_at = datetime.now(timezone.utc)
    created.details = {}
    created.created_at = datetime.now(timezone.utc)

    svc.node_repository.get_by_id.return_value = node
    svc.probe_repository.get_latest_for_node.side_effect = [previous, created]
    svc.probe_repository.create.return_value = created
    svc.route_repository.list_active.return_value = []

    await svc.report(
        ProbeReportIn(
            node_id=node.id,
            source="ru-probe-1",
            is_reachable=False,
            error="timeout",
        )
    )

    svc.alert_service.send_probe_status_change.assert_not_awaited()


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
    svc.probe_repository.get_latest_for_node.return_value = None

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
    svc.probe_repository.get_latest_for_node.return_value = latest

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
    svc.probe_repository.get_latest_for_node.return_value = latest

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
    svc.probe_repository.get_latest_for_node.return_value = latest
    svc.probe_repository.list_recent.return_value = [latest, older_fail, older_ok]

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
    svc.probe_repository.get_latest_for_node.return_value = latest
    svc.probe_repository.list_recent.return_value = [latest]
    svc.placement_service.migrate_backend.return_value = migration

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
    gateway = _node(role="gateway")
    svc.node_repository.list.return_value = [backend_fail, backend_ok, backend_draining, gateway]

    fail_latest = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc))
    ok_latest = _probe(is_reachable=True, checked_at=datetime.now(timezone.utc))

    async def _latest_side_effect(*, node_id, source):
        if node_id == backend_fail.id:
            return fail_latest
        if node_id == backend_ok.id:
            return ok_latest
        return None

    svc.probe_repository.get_latest_for_node.side_effect = _latest_side_effect

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
    assert any(i.action == "skipped" and i.source_backend_id == gateway.id for i in out.items)


@pytest.mark.asyncio
async def test_auto_drain_and_migrate_backends_executes(async_session):
    svc = _drain_service()
    svc.node_repository = AsyncMock()
    svc.probe_repository = AsyncMock()
    svc.placement_service = AsyncMock()

    backend_fail = _node(role="backend")
    svc.node_repository.list.return_value = [backend_fail]
    fail_latest = _probe(is_reachable=False, checked_at=datetime.now(timezone.utc))
    svc.probe_repository.get_latest_for_node.return_value = fail_latest

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
    svc.probe_repository.get_latest_for_node.return_value = fail_latest
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
