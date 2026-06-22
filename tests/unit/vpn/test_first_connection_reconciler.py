from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from services.vpn.subscriptions.reconcilers.first_connection import (
    FirstConnectionReconciler,
)


def _make_reconciler():
    lock = MagicMock()
    lock.hold = MagicMock()
    return FirstConnectionReconciler(interval_sec=60, batch_size=50, tick_lock=lock)


def _fake_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    return session


async def test_tick_no_new_connections_returns_zero():
    rec = _make_reconciler()
    session = _fake_session()
    rec._session_maker = MagicMock(return_value=session)

    with patch(
        "services.vpn.subscriptions.reconcilers.first_connection.SubscriptionRepository"
    ) as RepoCls:
        RepoCls.return_value.stamp_first_connection = AsyncMock(return_value=[])
        result = await rec.tick()

    assert result == 0
    session.commit.assert_not_awaited()


async def test_tick_stamps_and_commits():
    rec = _make_reconciler()
    session = _fake_session()
    rec._session_maker = MagicMock(return_value=session)
    stamped = [uuid4(), uuid4()]

    with patch(
        "services.vpn.subscriptions.reconcilers.first_connection.SubscriptionRepository"
    ) as RepoCls:
        repo = RepoCls.return_value
        repo.stamp_first_connection = AsyncMock(return_value=stamped)
        result = await rec.tick()

    assert result == 2
    repo.stamp_first_connection.assert_awaited_once()
    session.commit.assert_awaited_once()
