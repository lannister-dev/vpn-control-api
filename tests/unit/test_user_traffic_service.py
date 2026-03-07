from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.traffic.service import UserTrafficService


def _make_key(
        *,
        client_id: str,
        used_traffic_bytes: int = 0,
        last_reported_total_bytes: int = 0,
        traffic_limit_mb: int = 1000,
        is_revoked: bool = False,
):
    return SimpleNamespace(
        id=uuid4(),
        client_id=client_id,
        used_traffic_bytes=used_traffic_bytes,
        last_reported_total_bytes=last_reported_total_bytes,
        traffic_limit_mb=traffic_limit_mb,
        is_revoked=is_revoked,
        updated_at=None,
    )


@pytest.fixture()
def service(async_session):
    svc = UserTrafficService(async_session)
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.traffic_usage_repository = AsyncMock()
    return svc


class TestUserTrafficService:
    async def test_ingest_invalid_json_is_ignored(self, service):
        result = await service.ingest_users_traffic(b"{invalid")
        assert result == {"processed": 0, "revoked": 0}

    async def test_ingest_updates_delta(self, service):
        key = _make_key(client_id="client-a", used_traffic_bytes=100, last_reported_total_bytes=1000)
        service.key_repository.list_by_client_ids.return_value = [key]

        payload = b'[{"identifier":"client-a","uplink_bytes":10,"downlink_bytes":20,"total_bytes":1050}]'
        out = await service.ingest_users_traffic(payload)

        assert out == {"processed": 1, "revoked": 0}
        assert key.last_reported_total_bytes == 1050
        assert key.used_traffic_bytes == 150
        service.traffic_usage_repository.bulk_create.assert_awaited_once()
        service.placement_repository.set_desired_state_for_key.assert_not_awaited()

    async def test_ingest_handles_counter_reset(self, service):
        key = _make_key(client_id="client-a", used_traffic_bytes=500, last_reported_total_bytes=1200)
        service.key_repository.list_by_client_ids.return_value = [key]

        payload = b'[{"identifier":"client-a","uplink_bytes":5,"downlink_bytes":5,"total_bytes":100}]'
        out = await service.ingest_users_traffic(payload)

        assert out == {"processed": 1, "revoked": 0}
        assert key.last_reported_total_bytes == 100
        assert key.used_traffic_bytes == 600

    async def test_ingest_revokes_key_when_limit_reached(self, service):
        mib = 1024 * 1024
        key = _make_key(
            client_id="client-a",
            used_traffic_bytes=2 * mib - 10,
            last_reported_total_bytes=1000,
            traffic_limit_mb=2,
            is_revoked=False,
        )
        service.key_repository.list_by_client_ids.return_value = [key]

        payload = b'[{"identifier":"client-a","uplink_bytes":0,"downlink_bytes":20,"total_bytes":1020}]'
        out = await service.ingest_users_traffic(payload)

        assert out == {"processed": 1, "revoked": 1}
        assert key.is_revoked is True
        service.placement_repository.set_desired_state_for_key.assert_awaited_once()

    async def test_ingest_ignores_unknown_keys(self, service):
        service.key_repository.list_by_client_ids.return_value = []
        payload = b'[{"identifier":"unknown","uplink_bytes":1,"downlink_bytes":2,"total_bytes":3}]'
        out = await service.ingest_users_traffic(payload)
        assert out == {"processed": 0, "revoked": 0}

    async def test_cleanup_history_returns_deleted_rows(self, service):
        service.traffic_usage_repository.delete_older_than.return_value = 7
        deleted = await service.cleanup_history(retention_days=14)
        assert deleted == 7
