from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.placements.schemas import PlacementMigrateBackendIn
from services.placements.service import UserPlacementService


def _node(*, is_active=True, is_enabled=True, is_draining=False, role="backend"):
    n = MagicMock()
    n.id = uuid4()
    n.role = role
    n.region = "fi"
    n.is_active = is_active
    n.is_enabled = is_enabled
    n.is_draining = is_draining
    return n


def _placement(*, desired_state: str, op_version: int):
    p = MagicMock()
    p.id = uuid4()
    p.gateway_node_id = uuid4()
    p.desired_state = desired_state
    p.op_version = op_version
    return p


@pytest.mark.asyncio
async def test_migrate_backend_rejects_same_source_target(async_session):
    svc = UserPlacementService(async_session)

    backend_id = uuid4()
    payload = PlacementMigrateBackendIn(
        source_backend_id=backend_id,
        target_backend_id=backend_id,
    )

    with pytest.raises(HTTPException) as exc:
        await svc.migrate_backend(payload)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_migrate_backend_rejects_ineligible_target(async_session):
    svc = UserPlacementService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.backend_peer_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    source = _node()
    target = _node(is_draining=True)
    payload = PlacementMigrateBackendIn(
        source_backend_id=source.id,
        target_backend_id=target.id,
    )
    svc.node_repository.get_by_id = AsyncMock(side_effect=[source, target])

    with pytest.raises(HTTPException) as exc:
        await svc.migrate_backend(payload)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_migrate_backend_moves_only_active(async_session):
    svc = UserPlacementService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.backend_peer_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    source = _node()
    target = _node()
    payload = PlacementMigrateBackendIn(
        source_backend_id=source.id,
        target_backend_id=target.id,
        last_migration_reason="admin_manual",
    )
    svc.node_repository.get_by_id = AsyncMock(side_effect=[source, target])

    active = _placement(desired_state="active", op_version=3)
    inactive = _placement(desired_state="inactive", op_version=5)
    svc.placement_repository.list_active = AsyncMock(return_value=[active, inactive])
    svc.placement_repository.bulk_migrate_backend = AsyncMock(return_value=1)

    out = await svc.migrate_backend(payload)

    assert out.migrated_count == 1
    assert out.target_backend_id == target.id
    svc.backend_peer_repository.ensure_active_pair.assert_awaited_once()
    svc.placement_repository.bulk_migrate_backend.assert_awaited_once_with(
        placement_ids=[active.id],
        target_backend_id=target.id,
        last_migration_reason="admin_manual",
        updated_at=ANY,
    )


@pytest.mark.asyncio
async def test_migrate_backend_autoselects_target(async_session):
    svc = UserPlacementService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.backend_peer_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    source = _node()
    target = _node()
    payload = PlacementMigrateBackendIn(
        source_backend_id=source.id,
        target_backend_id=None,
        last_migration_reason="admin_manual",
    )
    svc.node_repository.get_by_id = AsyncMock(return_value=source)
    svc.routing_service.select_nodes = AsyncMock(return_value=[target])
    active = _placement(desired_state="active", op_version=1)
    svc.placement_repository.list_active = AsyncMock(return_value=[active])
    svc.placement_repository.bulk_migrate_backend = AsyncMock(return_value=1)

    out = await svc.migrate_backend(payload)

    assert out.target_backend_id == target.id
    svc.routing_service.select_nodes.assert_awaited_once()
    svc.backend_peer_repository.ensure_active_pair.assert_awaited_once_with(
        backend_node_id=target.id,
        gateway_node_id=active.gateway_node_id,
    )
    svc.placement_repository.bulk_migrate_backend.assert_awaited_once_with(
        placement_ids=[active.id],
        target_backend_id=target.id,
        last_migration_reason="admin_manual",
        updated_at=ANY,
    )


@pytest.mark.asyncio
async def test_migrate_backend_bulk_updates_active_and_deduplicates_gateway_peers(async_session):
    svc = UserPlacementService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.backend_peer_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    source = _node()
    target = _node()
    payload = PlacementMigrateBackendIn(
        source_backend_id=source.id,
        target_backend_id=target.id,
        last_migration_reason="admin_bulk",
    )
    svc.node_repository.get_by_id = AsyncMock(side_effect=[source, target])

    gw_a = uuid4()
    gw_b = uuid4()
    gw_c = uuid4()

    active: list[MagicMock] = []
    for i in range(12):
        placement = _placement(desired_state="active", op_version=i + 1)
        if i % 5 == 0:
            placement.gateway_node_id = None
        elif i % 2 == 0:
            placement.gateway_node_id = gw_a
        else:
            placement.gateway_node_id = gw_b
        active.append(placement)

    inactive = _placement(desired_state="inactive", op_version=99)
    inactive.gateway_node_id = gw_a
    svc.placement_repository.list_active = AsyncMock(return_value=[*active, inactive])
    svc.placement_repository.bulk_migrate_backend = AsyncMock(return_value=len(active))

    gw_existing = _node(role="gateway")
    gw_existing.id = gw_b
    gw_existing.public_domain = "gw-b.example"

    gw_extra = _node(role="gateway")
    gw_extra.id = gw_c
    gw_extra.public_domain = "gw-c.example"

    gw_no_domain = _node(role="gateway")
    gw_no_domain.public_domain = ""

    gw_draining = _node(role="gateway", is_draining=True)
    gw_draining.public_domain = "gw-drain.example"

    svc.node_repository.list_public = AsyncMock(
        return_value=[gw_existing, gw_extra, gw_no_domain, gw_draining]
    )

    out = await svc.migrate_backend(payload)

    assert out.migrated_count == len(active)
    svc.placement_repository.bulk_migrate_backend.assert_awaited_once()
    bulk_kwargs = svc.placement_repository.bulk_migrate_backend.await_args.kwargs
    assert set(bulk_kwargs["placement_ids"]) == {placement.id for placement in active}
    assert bulk_kwargs["target_backend_id"] == target.id
    assert bulk_kwargs["last_migration_reason"] == "admin_bulk"
    assert bulk_kwargs["updated_at"] is not None

    ensure_calls = svc.backend_peer_repository.ensure_active_pair.await_args_list
    assert len(ensure_calls) == 3
    actual_gateway_ids = {item.kwargs["gateway_node_id"] for item in ensure_calls}
    assert actual_gateway_ids == {gw_a, gw_b, gw_c}
    assert all(item.kwargs["backend_node_id"] == target.id for item in ensure_calls)
