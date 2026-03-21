from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.traffic.schemas import (
    TrafficHistoryItemOut,
    TrafficHistoryListOut,
    TrafficKeySummaryListOut,
    TrafficKeySummaryOut,
)
from services.traffic.service import TrafficAdminService


def _make_key(
    *,
    client_id: str = "client-a",
    user_id=None,
    used_traffic_bytes: int = 0,
    traffic_limit_mb: int = 1000,
    is_revoked: bool = False,
    protocol: str = "vless",
    transport: str = "ws",
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id or uuid4(),
        client_id=client_id,
        protocol=protocol,
        transport=transport,
        valid_until=now + timedelta(days=30),
        traffic_limit_mb=traffic_limit_mb,
        used_traffic_bytes=used_traffic_bytes,
        is_revoked=is_revoked,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_history_row(*, key_id=None, delta_bytes: int = 100, reported_total_bytes: int = 1000):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        key_id=key_id or uuid4(),
        delta_bytes=delta_bytes,
        reported_total_bytes=reported_total_bytes,
        created_at=now,
    )


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestTrafficSchemas:
    def test_traffic_key_summary_out_from_attributes(self):
        key = _make_key(client_id="test-key", used_traffic_bytes=5000, traffic_limit_mb=100)
        out = TrafficKeySummaryOut.model_validate(key)
        assert out.client_id == "test-key"
        assert out.used_traffic_bytes == 5000
        assert out.traffic_limit_mb == 100

    def test_traffic_key_summary_list_out(self):
        keys = [_make_key(client_id=f"key-{i}") for i in range(3)]
        items = [TrafficKeySummaryOut.model_validate(k) for k in keys]
        result = TrafficKeySummaryListOut(items=items, total=10, limit=50, offset=0)
        assert len(result.items) == 3
        assert result.total == 10

    def test_traffic_history_item_out(self):
        row = _make_history_row(delta_bytes=200, reported_total_bytes=2000)
        out = TrafficHistoryItemOut.model_validate(row)
        assert out.delta_bytes == 200
        assert out.reported_total_bytes == 2000

    def test_traffic_history_list_out_empty(self):
        result = TrafficHistoryListOut(items=[], total=0, limit=50, offset=0)
        assert result.items == []
        assert result.total == 0

    def test_traffic_key_summary_revoked(self):
        key = _make_key(is_revoked=True, used_traffic_bytes=1024 * 1024 * 100)
        out = TrafficKeySummaryOut.model_validate(key)
        assert out.is_revoked is True

    def test_traffic_key_summary_no_limit(self):
        key = _make_key(traffic_limit_mb=0)
        out = TrafficKeySummaryOut.model_validate(key)
        assert out.traffic_limit_mb == 0


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------

class TestTrafficUsageRepository:
    @pytest.fixture()
    def repo(self, async_session):
        from services.traffic.repository import TrafficUsageRepository
        return TrafficUsageRepository(async_session)

    async def test_list_by_key_id_calls_session(self, repo):
        key_id = uuid4()
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        repo.session.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        rows, total = await repo.list_by_key_id(key_id=key_id, limit=10, offset=0)
        assert total == 0
        assert rows == []
        assert repo.session.execute.await_count == 2

    async def test_list_by_key_id_with_date_filters(self, repo):
        key_id = uuid4()
        now = datetime.now(timezone.utc)
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        repo.session.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        rows, total = await repo.list_by_key_id(
            key_id=key_id,
            date_from=now - timedelta(days=7),
            date_to=now,
            limit=20,
            offset=0,
        )
        assert total == 5


class TestVpnKeyRepository:
    @pytest.fixture()
    def repo(self, async_session):
        from services.vpn.keys.repository import VpnKeyRepository
        return VpnKeyRepository(async_session)

    async def test_list_with_traffic_summary_calls_session(self, repo):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        repo.session.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        keys, total = await repo.list_with_traffic_summary(limit=10, offset=0)
        assert total == 0
        assert keys == []

    async def test_list_with_traffic_summary_with_filters(self, repo):
        user_id = uuid4()
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        repo.session.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        keys, total = await repo.list_with_traffic_summary(
            user_id=user_id,
            is_revoked=False,
            search="test",
            limit=20,
            offset=10,
        )
        assert total == 3


# ---------------------------------------------------------------------------
# TrafficAdminService tests
# ---------------------------------------------------------------------------

class TestTrafficAdminService:
    @pytest.fixture()
    def service(self, async_session):
        svc = TrafficAdminService(async_session)
        svc.key_repository = AsyncMock()
        svc.traffic_usage_repository = AsyncMock()
        return svc

    async def test_list_keys_returns_paginated_result(self, service):
        keys = [_make_key(client_id=f"k-{i}") for i in range(3)]
        service.key_repository.list_with_traffic_summary.return_value = (keys, 42)

        result = await service.list_keys_with_traffic(limit=10, offset=0)

        assert isinstance(result, TrafficKeySummaryListOut)
        assert len(result.items) == 3
        assert result.total == 42
        assert result.limit == 10
        assert result.offset == 0
        service.key_repository.list_with_traffic_summary.assert_awaited_once_with(
            user_id=None, is_revoked=None, search=None, limit=10, offset=0,
        )

    async def test_list_keys_passes_filters(self, service):
        uid = uuid4()
        service.key_repository.list_with_traffic_summary.return_value = ([], 0)

        result = await service.list_keys_with_traffic(
            user_id=uid, is_revoked=True, search="abc", limit=5, offset=10,
        )

        assert result.total == 0
        service.key_repository.list_with_traffic_summary.assert_awaited_once_with(
            user_id=uid, is_revoked=True, search="abc", limit=5, offset=10,
        )

    async def test_list_keys_empty(self, service):
        service.key_repository.list_with_traffic_summary.return_value = ([], 0)
        result = await service.list_keys_with_traffic()
        assert result.items == []
        assert result.total == 0

    async def test_get_history_returns_paginated_result(self, service):
        kid = uuid4()
        rows = [_make_history_row(key_id=kid, delta_bytes=i * 100) for i in range(1, 4)]
        service.traffic_usage_repository.list_by_key_id.return_value = (rows, 15)

        result = await service.get_key_traffic_history(key_id=kid, limit=20, offset=0)

        assert isinstance(result, TrafficHistoryListOut)
        assert len(result.items) == 3
        assert result.total == 15
        service.traffic_usage_repository.list_by_key_id.assert_awaited_once_with(
            key_id=kid, date_from=None, date_to=None, limit=20, offset=0,
        )

    async def test_get_history_with_date_range(self, service):
        kid = uuid4()
        now = datetime.now(timezone.utc)
        service.traffic_usage_repository.list_by_key_id.return_value = ([], 0)

        result = await service.get_key_traffic_history(
            key_id=kid, date_from=now - timedelta(days=7), date_to=now,
        )

        assert result.items == []
        assert result.total == 0
        call_kwargs = service.traffic_usage_repository.list_by_key_id.call_args.kwargs
        assert call_kwargs["date_from"] is not None
        assert call_kwargs["date_to"] is not None

    async def test_get_history_empty(self, service):
        kid = uuid4()
        service.traffic_usage_repository.list_by_key_id.return_value = ([], 0)

        result = await service.get_key_traffic_history(key_id=kid)

        assert result.items == []
        assert result.total == 0

    async def test_get_history_revoked_key_still_works(self, service):
        kid = uuid4()
        rows = [_make_history_row(key_id=kid)]
        service.traffic_usage_repository.list_by_key_id.return_value = (rows, 1)

        result = await service.get_key_traffic_history(key_id=kid)

        assert len(result.items) == 1
