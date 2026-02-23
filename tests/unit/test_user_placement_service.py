from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.placements.schemas import UserPlacementUpsertIn
from services.placements.service import UserPlacementService


@pytest.mark.asyncio
async def test_upsert_placement_key_not_found(async_session):
    svc = UserPlacementService(async_session)
    svc.key_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.key_repository.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await svc.upsert(
            UserPlacementUpsertIn(
                key_id=uuid4(),
                backend_node_id=uuid4(),
            )
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_upsert_placement_backend_not_found(async_session):
    svc = UserPlacementService(async_session)
    svc.key_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.key_repository.get_by_id.return_value = MagicMock()
    svc.node_repository.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await svc.upsert(
            UserPlacementUpsertIn(
                key_id=uuid4(),
                backend_node_id=uuid4(),
            )
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_upsert_placement_success(async_session):
    svc = UserPlacementService(async_session)
    svc.key_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    key = MagicMock()
    key.id = uuid4()
    backend = MagicMock()
    backend.id = uuid4()
    backend.role = "backend"

    placement = MagicMock()
    placement.id = uuid4()
    placement.key_id = key.id
    placement.backend_node_id = backend.id
    placement.desired_state = "active"
    placement.applied_state = "pending"
    placement.op_version = 1
    placement.applied_version = 0
    placement.sticky_until = None
    placement.last_migration_reason = None
    placement.is_active = True
    placement.created_at = datetime.now(timezone.utc)
    placement.updated_at = datetime.now(timezone.utc)

    svc.key_repository.get_by_id.return_value = key
    svc.node_repository.get_by_id.return_value = backend
    svc.placement_repository.upsert_set_pending.return_value = placement

    out = await svc.upsert(
        UserPlacementUpsertIn(
            key_id=key.id,
            backend_node_id=backend.id,
        )
    )
    assert out.key_id == key.id
    assert out.backend_node_id == backend.id
