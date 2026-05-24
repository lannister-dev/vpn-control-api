from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.admin.transport.router import transport_cleanup
from services.admin.transport.schemas import TransportCleanupOut


@pytest.mark.asyncio
async def test_transport_cleanup_router_contract():
    expected = TransportCleanupOut(
        deleted_outbox=7,
        deleted_events=19,
        retention_days=30,
    )
    service = SimpleNamespace(cleanup_old_data=AsyncMock(return_value=expected))

    out = await transport_cleanup(service=service)

    assert out == expected
    service.cleanup_old_data.assert_awaited_once_with()
