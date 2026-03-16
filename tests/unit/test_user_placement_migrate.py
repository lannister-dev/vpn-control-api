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
    p.key_id = uuid4()
    p.desired_state = desired_state
    p.op_version = op_version
    return p


@pytest.mark.asyncio
async def test_migrate_backend_rejects_same_source_target(async_session):
    svc = UserPlacementService(async_session)
    svc.node_agent_transport = AsyncMock()

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
    svc.routing_service = AsyncMock()
    svc.node_agent_transport = AsyncMock()

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
    svc.routing_service = AsyncMock()
    svc.node_agent_transport = AsyncMock()

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
    target_placement_id = uuid4()
    svc.placement_repository.list_active = AsyncMock(return_value=[active, inactive])
    svc.placement_repository.bulk_migrate_backend = AsyncMock(return_value=1)
    svc.placement_repository.list_active_ids_for_keys = AsyncMock(return_value=[target_placement_id])

    out = await svc.migrate_backend(payload)

    assert out.migrated_count == 1
    assert out.target_backend_id == target.id
    svc.placement_repository.bulk_migrate_backend.assert_awaited_once_with(
        placement_ids=[active.id],
        target_backend_id=target.id,
        last_migration_reason="admin_manual",
        updated_at=ANY,
    )
    svc.placement_repository.list_active_ids_for_keys.assert_awaited_once_with(
        key_ids=[active.key_id],
        backend_node_id=target.id,
    )
    svc.node_agent_transport.enqueue_for_placement_ids.assert_awaited_once_with([target_placement_id])


@pytest.mark.asyncio
async def test_migrate_backend_autoselects_target(async_session):
    svc = UserPlacementService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.routing_service = AsyncMock()
    svc.node_agent_transport = AsyncMock()

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
    svc.placement_repository.list_active_ids_for_keys = AsyncMock(return_value=[active.id])

    out = await svc.migrate_backend(payload)

    assert out.target_backend_id == target.id
    svc.routing_service.select_nodes.assert_awaited_once()
    svc.placement_repository.bulk_migrate_backend.assert_awaited_once_with(
        placement_ids=[active.id],
        target_backend_id=target.id,
        last_migration_reason="admin_manual",
        updated_at=ANY,
    )
    svc.node_agent_transport.enqueue_for_placement_ids.assert_awaited_once_with([active.id])


@pytest.mark.asyncio
async def test_migrate_backend_bulk_updates_active_only(async_session):
    svc = UserPlacementService(async_session)
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.routing_service = AsyncMock()
    svc.node_agent_transport = AsyncMock()

    source = _node()
    target = _node()
    payload = PlacementMigrateBackendIn(
        source_backend_id=source.id,
        target_backend_id=target.id,
        last_migration_reason="admin_bulk",
    )
    svc.node_repository.get_by_id = AsyncMock(side_effect=[source, target])

    active: list[MagicMock] = []
    for i in range(12):
        placement = _placement(desired_state="active", op_version=i + 1)
        active.append(placement)

    inactive = _placement(desired_state="inactive", op_version=99)
    svc.placement_repository.list_active = AsyncMock(return_value=[*active, inactive])
    svc.placement_repository.bulk_migrate_backend = AsyncMock(return_value=len(active))
    target_ids = [uuid4() for _ in active]
    svc.placement_repository.list_active_ids_for_keys = AsyncMock(return_value=target_ids)

    out = await svc.migrate_backend(payload)

    assert out.migrated_count == len(active)
    svc.placement_repository.bulk_migrate_backend.assert_awaited_once()
    bulk_kwargs = svc.placement_repository.bulk_migrate_backend.await_args.kwargs
    assert set(bulk_kwargs["placement_ids"]) == {placement.id for placement in active}
    assert bulk_kwargs["target_backend_id"] == target.id
    assert bulk_kwargs["last_migration_reason"] == "admin_bulk"
    assert bulk_kwargs["updated_at"] is not None
    svc.placement_repository.list_active_ids_for_keys.assert_awaited_once_with(
        key_ids=[placement.key_id for placement in active],
        backend_node_id=target.id,
    )
    svc.node_agent_transport.enqueue_for_placement_ids.assert_awaited_once_with(target_ids)
