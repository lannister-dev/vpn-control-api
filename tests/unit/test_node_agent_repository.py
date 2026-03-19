from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.nodes.agent.repository import NodeTransportStateRepository


class _ScalarOneResult:
    def __init__(self, row):
        self._row = row

    def scalar_one(self):
        return self._row


@pytest.mark.asyncio
async def test_reserve_snapshot_epoch_locks_state_row(async_session):
    repo = NodeTransportStateRepository(async_session)
    node_id = uuid4()
    state = MagicMock()
    state.current_epoch = 3
    state.last_snapshot_request_event_id = None
    state.last_snapshot_id = None

    repo.get_or_create = AsyncMock(return_value=state)
    async_session.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(state),
            MagicMock(),
        ]
    )

    epoch, snapshot_id = await repo.reserve_snapshot_epoch(
        node_id=node_id,
        request_event_id="req-1",
        snapshot_id="snap-1",
        snapshot_reason="xray_restart",
        requested_at=datetime.now(timezone.utc),
        generated_at=datetime.now(timezone.utc),
    )

    assert epoch == 4
    assert snapshot_id == "snap-1"
    select_stmt = async_session.execute.await_args_list[0].args[0]
    assert getattr(select_stmt, "_for_update_arg", None) is not None
