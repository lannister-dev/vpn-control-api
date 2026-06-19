from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.balancer.load_consumer import BackendLoadRebalanceConsumer
from services.config import BackendRebalanceConfig, NatsConfig


def _consumer(*, debounce_sec=60):
    return BackendLoadRebalanceConsumer(
        NatsConfig(), rebalance_config=BackendRebalanceConfig(debounce_sec=debounce_sec),
    )


def _session_maker():
    session = AsyncMock()
    session.has_pending_writes = MagicMock(return_value=False)

    @asynccontextmanager
    async def _cm():
        yield session

    return MagicMock(side_effect=lambda: _cm()), session


@pytest.mark.asyncio
async def test_handle_skips_within_debounce():
    c = _consumer(debounce_sec=60)
    c._last_rebalance_monotonic = 1_000_000.0
    msg = AsyncMock()
    with patch("services.balancer.load_consumer.time.monotonic", return_value=1_000_010.0), \
         patch("services.balancer.load_consumer.BackendRebalancer") as rb:
        await c._handle_message(b"{}", msg)
    msg.ack.assert_awaited_once()
    rb.assert_not_called()


@pytest.mark.asyncio
async def test_handle_runs_rebalance_after_debounce():
    c = _consumer(debounce_sec=60)
    c._last_rebalance_monotonic = 0.0
    msg = AsyncMock()
    maker, session = _session_maker()
    rebalance = AsyncMock(return_value=3)
    with patch("services.balancer.load_consumer.time.monotonic", return_value=1_000_000.0), \
         patch("services.balancer.load_consumer.AsyncDatabase.get_session_maker", return_value=maker), \
         patch("services.balancer.load_consumer.BackendRebalancer") as rb:
        rb.return_value.rebalance = rebalance
        await c._handle_message(b"{}", msg)
    rebalance.assert_awaited_once()
    assert c._last_rebalance_monotonic == 1_000_000.0
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_sets_debounce_even_when_no_moves():
    c = _consumer(debounce_sec=60)
    c._last_rebalance_monotonic = 0.0
    msg = AsyncMock()
    maker, _ = _session_maker()
    with patch("services.balancer.load_consumer.time.monotonic", return_value=500.0), \
         patch("services.balancer.load_consumer.AsyncDatabase.get_session_maker", return_value=maker), \
         patch("services.balancer.load_consumer.BackendRebalancer") as rb:
        rb.return_value.rebalance = AsyncMock(return_value=0)
        await c._handle_message(b"{}", msg)
    assert c._last_rebalance_monotonic == 500.0
