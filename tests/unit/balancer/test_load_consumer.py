from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.balancer.load_consumer import BackendLoadRebalanceConsumer
from services.config import BackendRebalanceConfig, NatsConfig


def _consumer(*, min_spread=5, debounce_sec=60):
    cfg = NatsConfig()
    return BackendLoadRebalanceConsumer(
        cfg, rebalance_config=BackendRebalanceConfig(debounce_sec=debounce_sec, min_spread=min_spread),
    )


def test_is_imbalanced_below_threshold():
    c = _consumer(min_spread=5)
    assert c._is_imbalanced({"backend-a": 10, "backend-b": 7}) is False


def test_is_imbalanced_at_threshold():
    c = _consumer(min_spread=5)
    assert c._is_imbalanced({"backend-a": 12, "backend-b": 7}) is True


def test_is_imbalanced_single_backend():
    c = _consumer(min_spread=1)
    assert c._is_imbalanced({"backend-a": 99}) is False


async def _one_session(*_a, **_k):
    yield AsyncMock()


@pytest.mark.asyncio
async def test_handle_skips_rebalance_within_debounce():
    c = _consumer(debounce_sec=60)
    c._last_rebalance_monotonic = 1_000_000.0
    msg = AsyncMock()
    with patch("services.balancer.load_consumer.time.monotonic", return_value=1_000_010.0), \
         patch("services.balancer.load_consumer.BackendBalancer.fetch_backend_loads", new=AsyncMock()) as loads, \
         patch("services.balancer.load_consumer.BackendRebalancer") as rb:
        await c._handle_message(b"{}", msg)
    msg.ack.assert_awaited_once()
    loads.assert_not_awaited()
    rb.assert_not_called()


@pytest.mark.asyncio
async def test_handle_rebalances_when_imbalanced():
    c = _consumer(debounce_sec=60, min_spread=5)
    c._last_rebalance_monotonic = 0.0
    msg = AsyncMock()
    rebalance = AsyncMock(return_value=3)
    with patch("services.balancer.load_consumer.time.monotonic", return_value=1_000_000.0), \
         patch("services.balancer.load_consumer.BackendBalancer.fetch_backend_loads",
               new=AsyncMock(return_value={"backend-a": 20, "backend-b": 2})), \
         patch("services.balancer.load_consumer.AsyncDatabase.get_session", new=_one_session), \
         patch("services.balancer.load_consumer.BackendRebalancer") as rb:
        rb.return_value.rebalance = rebalance
        await c._handle_message(b"{}", msg)
    rebalance.assert_awaited_once()
    assert c._last_rebalance_monotonic == 1_000_000.0


@pytest.mark.asyncio
async def test_handle_skips_when_balanced():
    c = _consumer(debounce_sec=60, min_spread=5)
    msg = AsyncMock()
    with patch("services.balancer.load_consumer.time.monotonic", return_value=1_000_000.0), \
         patch("services.balancer.load_consumer.BackendBalancer.fetch_backend_loads",
               new=AsyncMock(return_value={"backend-a": 10, "backend-b": 9})), \
         patch("services.balancer.load_consumer.BackendRebalancer") as rb:
        await c._handle_message(b"{}", msg)
    rb.assert_not_called()
