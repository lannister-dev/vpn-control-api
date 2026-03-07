from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.admin_status.router import get_admin_readiness, get_admin_status
from services.admin_status.schemas import (
    AdminNodeStatusOut,
    AdminReadinessCheckOut,
    AdminReadinessOut,
    AdminStatusOut,
    AdminStatusTotalsOut,
)
from services.nodes.schemas import NodeRole


@pytest.mark.asyncio
async def test_admin_status_router_contract():
    expected = AdminStatusOut(
        generated_at=datetime.now(timezone.utc),
        totals=AdminStatusTotalsOut(
            nodes_total=1,
            nodes_enabled=1,
            nodes_draining=0,
            nodes_healthy=1,
            placements_total=3,
        ),
        nodes=[
            AdminNodeStatusOut(
                id=uuid4(),
                name="be-1",
                role=NodeRole.backend,
                region="fi",
                public_domain="be-1.example.com",
                is_enabled=True,
                is_draining=False,
                capacity=100,
                is_healthy=True,
                last_seen_at=None,
                last_sync_at=None,
                placements_backend=3,
            )
        ],
    )
    service = SimpleNamespace(get_status=AsyncMock(return_value=expected))

    out = await get_admin_status(service=service)

    assert out == expected
    service.get_status.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_admin_readiness_router_contract():
    expected = AdminReadinessOut(
        generated_at=datetime.now(timezone.utc),
        ready=True,
        checks=[
            AdminReadinessCheckOut(
                name="active_profiles_artifact",
                ok=True,
                detail="active artifact found",
            ),
            AdminReadinessCheckOut(
                name="healthy_backend_nodes",
                ok=True,
                detail="healthy backends: 1",
            ),
            AdminReadinessCheckOut(
                name="resolvable_active_routes",
                ok=True,
                detail="resolved active routes: 3",
            ),
            AdminReadinessCheckOut(
                name="healthy_regions_route_coverage",
                ok=True,
                detail="regions covered: fi",
            ),
        ],
    )
    service = SimpleNamespace(get_readiness=AsyncMock(return_value=expected))

    out = await get_admin_readiness(service=service)

    assert out == expected
    service.get_readiness.assert_awaited_once_with()
