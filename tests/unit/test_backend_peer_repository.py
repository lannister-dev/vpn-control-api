from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from services.backend_peers.repository import BackendPeerRepository


@pytest.mark.asyncio
async def test_ensure_active_pair_create_race_returns_existing(async_session):
    repo = BackendPeerRepository(async_session)

    backend_node_id = uuid4()
    gateway_node_id = uuid4()

    existing = MagicMock()
    existing.status = "active"
    existing.is_active = True

    repo.get_by_pair = AsyncMock(side_effect=[None, existing])
    repo.create = AsyncMock(
        side_effect=IntegrityError(
            statement="insert into backend_peer",
            params={},
            orig=Exception("duplicate key"),
        )
    )
    repo.update_by_id = AsyncMock()

    out = await repo.ensure_active_pair(
        backend_node_id=backend_node_id,
        gateway_node_id=gateway_node_id,
    )

    assert out is existing
    repo.update_by_id.assert_not_awaited()
