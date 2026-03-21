from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.traffic.service import UserTrafficService


def _make_key(
        *,
        client_id: str,
        used_traffic_bytes: int = 0,
        traffic_limit_mb: int = 1000,
        is_revoked: bool = False,
        subscription_id=None,
):
    return SimpleNamespace(
        id=uuid4(),
        client_id=client_id,
        used_traffic_bytes=used_traffic_bytes,
        traffic_limit_mb=traffic_limit_mb,
        is_revoked=is_revoked,
        subscription_id=subscription_id,
        updated_at=None,
    )


def _make_counter(*, key_id, node_id="_unknown", last_reported_total_bytes=0):
    return SimpleNamespace(
        key_id=key_id,
        node_id=node_id,
        last_reported_total_bytes=last_reported_total_bytes,
        updated_at=None,
    )


def _make_plan(*, traffic_limit_bytes: int = 0, reset_strategy: str = "NO_RESET"):
    return SimpleNamespace(
        traffic_limit_bytes=traffic_limit_bytes,
        reset_strategy=reset_strategy,
    )


def _make_subscription(*, sub_id=None, plan=None, used_traffic_bytes: int = 0,
                        lifetime_used_traffic_bytes: int = 0):
    return SimpleNamespace(
        id=sub_id or uuid4(),
        plan=plan,
        used_traffic_bytes=used_traffic_bytes,
        lifetime_used_traffic_bytes=lifetime_used_traffic_bytes,
        updated_at=None,
    )


def _counters_dict(counters):
    """Build {(key_id, node_id): counter} dict from a list of counters."""
    return {(c.key_id, c.node_id): c for c in counters}


@pytest.fixture()
def service(async_session):
    svc = UserTrafficService(async_session)
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.traffic_usage_repository = AsyncMock()
    svc.subscription_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    svc.node_counter_repository = AsyncMock()
    svc.node_counter_repository.get_counters_for_keys.return_value = {}
    svc.node_counter_repository.create.side_effect = lambda data: SimpleNamespace(**data, updated_at=None)
    return svc


class TestUserTrafficService:
    async def test_ingest_invalid_json_is_ignored(self, service):
        result = await service.ingest_users_traffic(b"{invalid")
        assert result == {"processed": 0, "revoked": 0}

    async def test_ingest_updates_delta(self, service):
        key = _make_key(client_id="client-a", used_traffic_bytes=100)
        counter = _make_counter(key_id=key.id, last_reported_total_bytes=1000)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.node_counter_repository.get_counters_for_keys.return_value = _counters_dict([counter])

        payload = b'[{"identifier":"client-a","uplink_bytes":10,"downlink_bytes":20,"total_bytes":1050}]'
        out = await service.ingest_users_traffic(payload)

        assert out == {"processed": 1, "revoked": 0}
        assert counter.last_reported_total_bytes == 1050
        assert key.used_traffic_bytes == 150
        service.traffic_usage_repository.bulk_create.assert_awaited_once()
        service.placement_repository.set_desired_state_for_key.assert_not_awaited()

    async def test_ingest_handles_counter_reset(self, service):
        key = _make_key(client_id="client-a", used_traffic_bytes=500)
        counter = _make_counter(key_id=key.id, last_reported_total_bytes=1200)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.node_counter_repository.get_counters_for_keys.return_value = _counters_dict([counter])

        payload = b'[{"identifier":"client-a","uplink_bytes":5,"downlink_bytes":5,"total_bytes":100}]'
        out = await service.ingest_users_traffic(payload)

        assert out == {"processed": 1, "revoked": 0}
        assert counter.last_reported_total_bytes == 100
        assert key.used_traffic_bytes == 600

    async def test_ingest_revokes_key_when_limit_reached(self, service):
        mib = 1024 * 1024
        key = _make_key(
            client_id="client-a",
            used_traffic_bytes=2 * mib - 10,
            traffic_limit_mb=2,
            is_revoked=False,
        )
        counter = _make_counter(key_id=key.id, last_reported_total_bytes=1000)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.node_counter_repository.get_counters_for_keys.return_value = _counters_dict([counter])

        payload = b'[{"identifier":"client-a","uplink_bytes":0,"downlink_bytes":20,"total_bytes":1020}]'
        out = await service.ingest_users_traffic(payload)

        assert out == {"processed": 1, "revoked": 1}
        assert key.is_revoked is True
        service.placement_repository.set_desired_state_for_key.assert_awaited_once()
        service.node_agent_transport.enqueue_for_key_state.assert_awaited_once()

    async def test_ingest_ignores_unknown_keys(self, service):
        service.key_repository.list_by_client_ids.return_value = []
        payload = b'[{"identifier":"unknown","uplink_bytes":1,"downlink_bytes":2,"total_bytes":3}]'
        out = await service.ingest_users_traffic(payload)
        assert out == {"processed": 0, "revoked": 0}

    async def test_cleanup_history_returns_deleted_rows(self, service):
        service.traffic_usage_repository.delete_older_than.return_value = 7
        deleted = await service.cleanup_history(retention_days=14)
        assert deleted == 7

    async def test_first_report_creates_counter(self, service):
        """First traffic report for a key creates a new per-node counter."""
        key = _make_key(client_id="c1")
        service.key_repository.list_by_client_ids.return_value = [key]

        payload = json.dumps([{"identifier": "c1", "total_bytes": 5000}]).encode()
        out = await service.ingest_users_traffic(payload)

        assert out["processed"] == 1
        assert key.used_traffic_bytes == 5000
        service.node_counter_repository.create.assert_called_once()

    async def test_multi_node_no_double_count(self, service):
        """Two nodes reporting for the same key should NOT double-count."""
        key = _make_key(client_id="c1")
        counter_a = _make_counter(key_id=key.id, node_id="node-A", last_reported_total_bytes=1000)
        counter_b = _make_counter(key_id=key.id, node_id="node-B", last_reported_total_bytes=500)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.node_counter_repository.get_counters_for_keys.return_value = _counters_dict([counter_a, counter_b])

        # Node A reports 1200 (delta = 200), Node B reports 700 (delta = 200)
        payload = json.dumps([
            {"identifier": "c1", "total_bytes": 1200, "node_id": "node-A"},
            {"identifier": "c1", "total_bytes": 700, "node_id": "node-B"},
        ]).encode()
        out = await service.ingest_users_traffic(payload)

        assert out["processed"] == 2
        assert key.used_traffic_bytes == 400  # 200 + 200
        assert counter_a.last_reported_total_bytes == 1200
        assert counter_b.last_reported_total_bytes == 700

    async def test_multi_node_alternating_no_false_reset(self, service):
        """Alternating reports from two nodes must NOT trigger false counter resets."""
        key = _make_key(client_id="c1")
        counter_a = _make_counter(key_id=key.id, node_id="node-A", last_reported_total_bytes=38_000_000)
        counter_b = _make_counter(key_id=key.id, node_id="node-B", last_reported_total_bytes=1_300_000_000)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.node_counter_repository.get_counters_for_keys.return_value = _counters_dict([counter_a, counter_b])

        # Node B reports slightly more, Node A reports slightly more — no false resets
        payload = json.dumps([
            {"identifier": "c1", "total_bytes": 1_310_000_000, "node_id": "node-B"},
            {"identifier": "c1", "total_bytes": 39_000_000, "node_id": "node-A"},
        ]).encode()
        out = await service.ingest_users_traffic(payload)

        assert out["processed"] == 2
        expected_delta = (1_310_000_000 - 1_300_000_000) + (39_000_000 - 38_000_000)
        assert key.used_traffic_bytes == expected_delta  # 11_000_000


class TestSubscriptionTrafficLimits:
    """Tests for plan-based subscription-level traffic enforcement."""

    async def test_subscription_traffic_aggregated_from_keys(self, service):
        """Delta from key is propagated to subscription counters."""
        sub_id = uuid4()
        plan = _make_plan(traffic_limit_bytes=10 * 1024 * 1024 * 1024)  # 10 GB
        sub = _make_subscription(sub_id=sub_id, plan=plan)
        key = _make_key(
            client_id="c1",
            subscription_id=sub_id,
        )
        counter = _make_counter(key_id=key.id, last_reported_total_bytes=1000)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]
        service.node_counter_repository.get_counters_for_keys.return_value = _counters_dict([counter])

        payload = json.dumps([{"identifier": "c1", "total_bytes": 1500}]).encode()
        out = await service.ingest_users_traffic(payload)

        assert out["processed"] == 1
        assert sub.used_traffic_bytes == 500
        assert sub.lifetime_used_traffic_bytes == 500

    async def test_subscription_unlimited_plan_no_revoke(self, service):
        """Plan with traffic_limit_bytes=0 (unlimited) never revokes."""
        sub_id = uuid4()
        plan = _make_plan(traffic_limit_bytes=0)
        sub = _make_subscription(sub_id=sub_id, plan=plan, used_traffic_bytes=999_999_999)
        key = _make_key(
            client_id="c1",
            subscription_id=sub_id,
        )
        service.key_repository.list_by_client_ids.return_value = [key]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]

        payload = json.dumps([{"identifier": "c1", "total_bytes": 5000}]).encode()
        out = await service.ingest_users_traffic(payload)

        assert out["processed"] == 1
        assert out["revoked"] == 0
        service.key_repository.list_active_by_subscription_id.assert_not_awaited()

    async def test_subscription_no_plan_no_revoke(self, service):
        """Subscription without plan — no subscription-level enforcement."""
        sub_id = uuid4()
        sub = _make_subscription(sub_id=sub_id, plan=None)
        key = _make_key(
            client_id="c1",
            traffic_limit_mb=0,  # also no per-key limit
            subscription_id=sub_id,
        )
        service.key_repository.list_by_client_ids.return_value = [key]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]

        payload = json.dumps([{"identifier": "c1", "total_bytes": 99999}]).encode()
        out = await service.ingest_users_traffic(payload)

        assert out["processed"] == 1
        assert out["revoked"] == 0

    async def test_subscription_limit_exceeded_revokes_all_keys(self, service):
        """When subscription exceeds plan limit, ALL its active keys are revoked."""
        sub_id = uuid4()
        limit = 1024 * 1024  # 1 MB
        plan = _make_plan(traffic_limit_bytes=limit)
        sub = _make_subscription(sub_id=sub_id, plan=plan, used_traffic_bytes=limit - 100)

        key1 = _make_key(client_id="c1", subscription_id=sub_id)
        # key2 is another active key of this subscription (not in current batch)
        key2 = _make_key(client_id="c2", subscription_id=sub_id)

        service.key_repository.list_by_client_ids.return_value = [key1]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]
        service.key_repository.list_active_by_subscription_id.return_value = [key1, key2]

        payload = json.dumps([{"identifier": "c1", "total_bytes": 200}]).encode()
        out = await service.ingest_users_traffic(payload)

        assert out["revoked"] == 2
        assert key1.is_revoked is True
        assert key2.is_revoked is True
        assert service.placement_repository.set_desired_state_for_key.await_count == 2
        assert service.node_agent_transport.enqueue_for_key_state.await_count == 2

    async def test_subscription_keys_skip_per_key_fallback(self, service):
        """Keys with subscription_id skip the per-key limit fallback (Phase 3)."""
        sub_id = uuid4()
        plan = _make_plan(traffic_limit_bytes=0)  # unlimited
        sub = _make_subscription(sub_id=sub_id, plan=plan)

        # Key has a per-key limit of 1 MB but belongs to an unlimited subscription
        mib = 1024 * 1024
        key = _make_key(
            client_id="c1",
            used_traffic_bytes=mib - 10,
            traffic_limit_mb=1,  # 1 MB per-key limit
            subscription_id=sub_id,
        )
        service.key_repository.list_by_client_ids.return_value = [key]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]

        payload = json.dumps([{"identifier": "c1", "total_bytes": 100}]).encode()
        out = await service.ingest_users_traffic(payload)

        # Should NOT be revoked — subscription is unlimited, per-key check is skipped
        assert out["revoked"] == 0
        assert key.is_revoked is False

    async def test_per_key_fallback_for_standalone_keys(self, service):
        """Keys without subscription_id use per-key traffic_limit_mb check."""
        mib = 1024 * 1024
        key = _make_key(
            client_id="c1",
            used_traffic_bytes=2 * mib - 10,
            traffic_limit_mb=2,
            subscription_id=None,
        )
        counter = _make_counter(key_id=key.id, last_reported_total_bytes=1000)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.node_counter_repository.get_counters_for_keys.return_value = _counters_dict([counter])

        payload = json.dumps([{"identifier": "c1", "total_bytes": 1020}]).encode()
        out = await service.ingest_users_traffic(payload)

        assert out["revoked"] == 1
        assert key.is_revoked is True

    async def test_multiple_keys_same_subscription_aggregated(self, service):
        """Deltas from multiple keys of one subscription are summed."""
        sub_id = uuid4()
        limit = 1000
        plan = _make_plan(traffic_limit_bytes=limit)
        sub = _make_subscription(sub_id=sub_id, plan=plan, used_traffic_bytes=0)

        key1 = _make_key(client_id="c1", subscription_id=sub_id)
        key2 = _make_key(client_id="c2", subscription_id=sub_id)

        service.key_repository.list_by_client_ids.return_value = [key1, key2]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]
        service.key_repository.list_active_by_subscription_id.return_value = [key1, key2]

        payload = json.dumps([
            {"identifier": "c1", "total_bytes": 600},
            {"identifier": "c2", "total_bytes": 500},
        ]).encode()
        out = await service.ingest_users_traffic(payload)

        # 600 + 500 = 1100 > 1000 limit
        assert sub.used_traffic_bytes == 1100
        assert sub.lifetime_used_traffic_bytes == 1100
        assert out["revoked"] == 2
        assert key1.is_revoked is True
        assert key2.is_revoked is True
