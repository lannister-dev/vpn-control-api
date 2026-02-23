from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.admin_ops.router import admin_migrate_backend, admin_set_route_health
from services.admin_ops.schemas import AdminSetRouteHealthIn
from services.placements.schemas import PlacementMigrateBackendIn, PlacementMigrateBackendOut
from services.routes.schemas import RouteHealthAction, RouteOut


@pytest.mark.asyncio
async def test_admin_migrate_backend_contract():
    source_backend_id = uuid4()
    target_backend_id = uuid4()
    placement_service = SimpleNamespace(
        migrate_backend=AsyncMock(
            return_value=PlacementMigrateBackendOut(
                source_backend_id=source_backend_id,
                target_backend_id=target_backend_id,
                migrated_count=3,
            )
        )
    )

    out = await admin_migrate_backend(
        payload=PlacementMigrateBackendIn(
            source_backend_id=source_backend_id,
            target_backend_id=target_backend_id,
            last_migration_reason="admin_manual",
        ),
        placement_service=placement_service,
    )

    assert out.source_backend_id == source_backend_id
    assert out.target_backend_id == target_backend_id
    assert out.migrated_count == 3
    placement_service.migrate_backend.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_set_route_health_contract():
    route_id = uuid4()
    route_service = SimpleNamespace(
        update_route_health=AsyncMock(
            return_value=RouteOut(
                id=route_id,
                name="be1-reality-google",
                node_id=uuid4(),
                transport_profile_id=uuid4(),
                health_status="blocked",
                base_weight=40,
                effective_weight=0,
                cooldown_until=None,
                warmup_stage=None,
                warmup_started_at=None,
                is_active=True,
                created_at="2026-02-20T00:00:00Z",
                updated_at="2026-02-20T00:00:00Z",
            )
        )
    )

    out = await admin_set_route_health(
        payload=AdminSetRouteHealthIn(
            route_id=route_id,
            action=RouteHealthAction.block,
            cooldown_hours=6,
        ),
        route_service=route_service,
    )

    assert out.id == route_id
    route_service.update_route_health.assert_awaited_once()
    args = route_service.update_route_health.await_args.args
    assert args[0] == route_id
    assert args[1].action == RouteHealthAction.block
    assert args[1].cooldown_hours == 6
