from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.placements.router import list_placements
from services.placements.service import UserPlacementService


@pytest.mark.asyncio
async def test_list_placements_router_passes_limit():
    service = MagicMock()
    service.list_placements = AsyncMock(return_value=[])
    backend_node_id = uuid4()

    out = await list_placements(
        backend_node_id=backend_node_id,
        limit=321,
        service=service,
    )

    assert out == []
    service.list_placements.assert_awaited_once_with(
        backend_node_id=backend_node_id,
        limit=321,
    )


@pytest.mark.asyncio
async def test_placement_service_passes_limit_to_repository(async_session):
    svc = UserPlacementService(async_session)
    svc.placement_repository = AsyncMock()
    svc.placement_repository.list_active.return_value = []

    out = await svc.list_placements(limit=111)

    assert out == []
    svc.placement_repository.list_active.assert_awaited_once_with(
        backend_node_id=None,
        limit=111,
    )

