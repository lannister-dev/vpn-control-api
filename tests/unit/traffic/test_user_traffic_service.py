from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.traffic.users.schemas import UserTrafficIn
from services.traffic.users.service import UserTrafficService


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


def _make_plan(*, traffic_limit_bytes: int = 0, reset_strategy: str = "NO_RESET"):
    return SimpleNamespace(
        traffic_limit_bytes=traffic_limit_bytes,
        reset_strategy=reset_strategy,
    )


def _make_subscription(*, sub_id=None, user_id=None, plan=None, used_traffic_bytes: int = 0,
                        lifetime_used_traffic_bytes: int = 0,
                        traffic_warning_threshold_pct: int = 0):
    return SimpleNamespace(
        id=sub_id or uuid4(),
        user_id=user_id or uuid4(),
        plan=plan,
        used_traffic_bytes=used_traffic_bytes,
        lifetime_used_traffic_bytes=lifetime_used_traffic_bytes,
        traffic_warning_threshold_pct=traffic_warning_threshold_pct,
        updated_at=None,
    )


def _items(*entries) -> list[UserTrafficIn]:
    """Build list of UserTrafficIn from (identifier, delta_bytes) tuples."""
    return [UserTrafficIn(identifier=e[0], delta_bytes=e[1]) for e in entries]


@pytest.fixture()
def service(async_session):
    svc = UserTrafficService(async_session)
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.traffic_usage_repository = AsyncMock()
    svc.subscription_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    return svc


class TestUserTrafficService:
    async def test_ingest_empty_items(self, service):
        result = await service.ingest_users_traffic([])
        assert result == {"processed": 0, "revoked": 0}

    async def test_ingest_applies_delta(self, service):
        key = _make_key(client_id="client-a", used_traffic_bytes=100)
        service.key_repository.list_by_client_ids.return_value = [key]

        out = await service.ingest_users_traffic(_items(("client-a", 50)))

        assert out == {"processed": 1, "revoked": 0}
        assert key.used_traffic_bytes == 150
        service.traffic_usage_repository.bulk_create.assert_awaited_once()

    async def test_ingest_zero_delta_ignored(self, service):
        key = _make_key(client_id="client-a", used_traffic_bytes=100)
        service.key_repository.list_by_client_ids.return_value = [key]

        out = await service.ingest_users_traffic(_items(("client-a", 0)))

        assert out == {"processed": 0, "revoked": 0}
        assert key.used_traffic_bytes == 100

    async def test_ingest_revokes_key_when_limit_reached(self, service):
        mib = 1024 * 1024
        key = _make_key(
            client_id="client-a",
            used_traffic_bytes=2 * mib - 10,
            traffic_limit_mb=2,
            is_revoked=False,
        )
        service.key_repository.list_by_client_ids.return_value = [key]

        out = await service.ingest_users_traffic(_items(("client-a", 20)))

        assert out == {"processed": 1, "revoked": 1}
        assert key.is_revoked is True
        service.placement_repository.set_desired_state_for_key.assert_awaited_once()
        service.node_agent_transport.enqueue_for_key_state.assert_awaited_once()

    async def test_ingest_ignores_unknown_keys(self, service):
        service.key_repository.list_by_client_ids.return_value = []

        out = await service.ingest_users_traffic(_items(("unknown", 100)))

        assert out == {"processed": 0, "revoked": 0}

    async def test_cleanup_history_returns_deleted_rows(self, service):
        service.traffic_usage_repository.delete_older_than.return_value = 7
        deleted = await service.cleanup_history(retention_days=14)
        assert deleted == 7

    async def test_multi_node_deltas_summed(self, service):
        """Deltas from multiple nodes simply sum up — no counter tracking needed."""
        key = _make_key(client_id="c1")
        service.key_repository.list_by_client_ids.return_value = [key]

        out = await service.ingest_users_traffic(_items(("c1", 200), ("c1", 300)))

        assert out == {"processed": 2, "revoked": 0}
        assert key.used_traffic_bytes == 500


class TestSubscriptionTrafficLimits:
    """Tests for plan-based subscription-level traffic enforcement."""

    async def test_subscription_traffic_aggregated_from_keys(self, service):
        """Delta from key is propagated to subscription counters."""
        sub_id = uuid4()
        plan = _make_plan(traffic_limit_bytes=10 * 1024 * 1024 * 1024)  # 10 GB
        sub = _make_subscription(sub_id=sub_id, plan=plan)
        key = _make_key(client_id="c1", subscription_id=sub_id)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]

        out = await service.ingest_users_traffic(_items(("c1", 500)))

        assert out == {"processed": 1, "revoked": 0}
        assert sub.used_traffic_bytes == 500
        assert sub.lifetime_used_traffic_bytes == 500

    async def test_subscription_unlimited_plan_no_revoke(self, service):
        """Plan with traffic_limit_bytes=0 (unlimited) never revokes."""
        sub_id = uuid4()
        plan = _make_plan(traffic_limit_bytes=0)
        sub = _make_subscription(sub_id=sub_id, plan=plan, used_traffic_bytes=999_999_999)
        key = _make_key(client_id="c1", subscription_id=sub_id)
        service.key_repository.list_by_client_ids.return_value = [key]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]

        out = await service.ingest_users_traffic(_items(("c1", 5000)))

        assert out == {"processed": 1, "revoked": 0}
        service.key_repository.list_active_by_subscription_id.assert_not_awaited()

    async def test_subscription_no_plan_no_revoke(self, service):
        """Subscription without plan — no subscription-level enforcement."""
        sub_id = uuid4()
        sub = _make_subscription(sub_id=sub_id, plan=None)
        key = _make_key(
            client_id="c1",
            traffic_limit_mb=0,
            subscription_id=sub_id,
        )
        service.key_repository.list_by_client_ids.return_value = [key]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]

        out = await service.ingest_users_traffic(_items(("c1", 99999)))

        assert out == {"processed": 1, "revoked": 0}

    async def test_subscription_limit_exceeded_revokes_all_keys(self, service):
        """When subscription exceeds plan limit, ALL its active keys are revoked."""
        sub_id = uuid4()
        limit = 1024 * 1024  # 1 MB
        plan = _make_plan(traffic_limit_bytes=limit)
        sub = _make_subscription(sub_id=sub_id, plan=plan, used_traffic_bytes=limit - 100)

        key1 = _make_key(client_id="c1", subscription_id=sub_id)
        key2 = _make_key(client_id="c2", subscription_id=sub_id)

        service.key_repository.list_by_client_ids.return_value = [key1]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]
        service.key_repository.list_active_by_subscription_id.return_value = [key1, key2]

        out = await service.ingest_users_traffic(_items(("c1", 200)))

        assert out["revoked"] == 2
        assert key1.is_revoked is True
        assert key2.is_revoked is True
        assert service.placement_repository.set_desired_state_for_key.await_count == 2
        assert service.node_agent_transport.enqueue_for_key_state.await_count == 2

    async def test_subscription_keys_skip_per_key_fallback(self, service):
        """Keys with subscription_id skip the per-key limit fallback."""
        sub_id = uuid4()
        plan = _make_plan(traffic_limit_bytes=0)  # unlimited
        sub = _make_subscription(sub_id=sub_id, plan=plan)

        mib = 1024 * 1024
        key = _make_key(
            client_id="c1",
            used_traffic_bytes=mib - 10,
            traffic_limit_mb=1,
            subscription_id=sub_id,
        )
        service.key_repository.list_by_client_ids.return_value = [key]
        service.subscription_repository.list_by_ids_with_plan.return_value = [sub]

        out = await service.ingest_users_traffic(_items(("c1", 100)))

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
        service.key_repository.list_by_client_ids.return_value = [key]

        out = await service.ingest_users_traffic(_items(("c1", 20)))

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

        out = await service.ingest_users_traffic(_items(("c1", 600), ("c2", 500)))

        # 600 + 500 = 1100 > 1000 limit
        assert sub.used_traffic_bytes == 1100
        assert sub.lifetime_used_traffic_bytes == 1100
        assert out["revoked"] == 2
        assert key1.is_revoked is True
        assert key2.is_revoked is True
