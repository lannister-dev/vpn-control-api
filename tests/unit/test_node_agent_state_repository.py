from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.nodes.repository import NodeAgentStateRepository


@pytest.mark.asyncio
async def test_upsert_does_not_commit_inside_repository():
    session = AsyncMock()
    repo = NodeAgentStateRepository(session)

    await repo.upsert(
        {
            "node_id": uuid4(),
            "agent_version": "1.2.3",
            "is_healthy": True,
            "last_seen_at": datetime.now(timezone.utc),
            "details": {},
        }
    )

    session.execute.assert_awaited_once()
    session.commit.assert_not_awaited()
