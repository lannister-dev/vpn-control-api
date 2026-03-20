from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.admin_transport.service import AdminTransportService
from services.config import TransportConfig


@pytest.mark.asyncio
async def test_cleanup_old_data_returns_deleted_counts(async_session):
    svc = AdminTransportService(async_session)
    svc.repo = AsyncMock()
    svc.repo.delete_published_outbox_older_than = AsyncMock(return_value=5)
    svc.repo.delete_events_older_than = AsyncMock(return_value=13)
    svc._transport_settings = TransportConfig(
        cleanup_enabled=True,
        cleanup_tick_sec=600,
        retention_days=30,
    )

    out = await svc.cleanup_old_data()

    assert out.deleted_outbox == 5
    assert out.deleted_events == 13
    assert out.retention_days == 30
    svc.repo.delete_published_outbox_older_than.assert_awaited_once()
    svc.repo.delete_events_older_than.assert_awaited_once()
    async_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_old_data_skips_commit_when_nothing_deleted(async_session):
    svc = AdminTransportService(async_session)
    svc.repo = AsyncMock()
    svc.repo.delete_published_outbox_older_than = AsyncMock(return_value=0)
    svc.repo.delete_events_older_than = AsyncMock(return_value=0)
    svc._transport_settings = TransportConfig(
        cleanup_enabled=True,
        cleanup_tick_sec=600,
        retention_days=30,
    )

    out = await svc.cleanup_old_data()

    assert out.deleted_outbox == 0
    assert out.deleted_events == 0
    async_session.commit.assert_not_awaited()
