from __future__ import annotations

import os

# Set dummy env vars BEFORE any project module is imported.
# This prevents environs.EnvError during test collection in CI
# where no .env file exists.
_DUMMY_ENV = {
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "test",
    "DB_USER": "test",
    "DB_PASSWORD": "test",
    "SSL_PATH": "",
    "REDIS_BROKER_URL": "redis://localhost:6379/0",
    "ADMIN_API_KEY_HASH": "0" * 64,
    "PROFILES_ALLOW_EMPTY_REGISTRY_ON_STARTUP": "true",
    "DOCS_PASSWORD_HASH": "test",
    "BOOTSTRAP_TOKEN_HASH": "test",
    "PROBE_TOKEN_HASH": "1" * 64,
    "PROBE_TARGET_PORT": "443",
    "PROBE_RETENTION_DAYS": "30",
}

for key, value in _DUMMY_ENV.items():
    os.environ.setdefault(key, value)

from services.config import get_settings

get_settings.cache_clear()

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.profiles.registry import ProfileRegistry


@pytest.fixture(autouse=True)
def _reset_profile_registry():
    """Reset the global ProfileRegistry before each test."""
    ProfileRegistry.reset()
    yield
    ProfileRegistry.reset()


_NODE_POLICY_DEFAULTS = dict(
    stale_after_sec=90,
    heartbeat_unhealthy_drain_threshold=5,
    heartbeat_healthy_undrain_threshold=3,
    auto_heal_enabled=False,
    auto_heal_tick_sec=60,
    auto_heal_max_nodes=20,
    auto_heal_drain_cooldown_sec=180,
    auto_undrain_enabled=False,
    placement_error_retry_enabled=True,
    placement_error_retry_tick_sec=120,
    placement_error_retry_after_sec=120,
    placement_rebalance_enabled=False,
    placement_rebalance_tick_sec=120,
    placement_rebalance_batch_size=200,
    entry_apply_fail_threshold=3,
    entry_apply_fail_unhealthy=True,
    entry_auto_drain_enabled=True,
    entry_auto_drain_tick_sec=60,
    entry_auto_drain_probe_failures=3,
    entry_auto_drain_max_nodes=50,
    entry_auto_drain_reason="entry_auto_drain",
    entry_auto_undrain_enabled=True,
    entry_auto_undrain_healthy_ticks=3,
)


@pytest.fixture(autouse=True)
def _stub_node_policy():
    policy = SimpleNamespace(**_NODE_POLICY_DEFAULTS)
    repo_stub = SimpleNamespace(list=AsyncMock(return_value=[policy]))
    with patch(
        "services.nodes.policy.repository.NodePolicyRepository",
        return_value=repo_stub,
    ):
        yield


@pytest.fixture(autouse=True)
def _stub_subscription_cache_invalidator():
    invalidator_stub = SimpleNamespace(
        invalidate_by_token_hashes=AsyncMock(return_value=0),
        invalidate_by_subscription_ids=AsyncMock(return_value=0),
        invalidate_by_key_ids=AsyncMock(return_value=0),
    )
    with patch(
        "services.vpn.subscriptions.cache.SubscriptionCacheInvalidator",
        return_value=invalidator_stub,
    ), patch(
        "services.vpn.keys.reconcilers.expiration.SubscriptionCacheInvalidator",
        return_value=invalidator_stub,
    ), patch(
        "services.vpn.subscriptions.reconcilers.expiration.SubscriptionCacheInvalidator",
        return_value=invalidator_stub,
    ), patch(
        "services.vpn.keys.service.SubscriptionCacheInvalidator",
        return_value=invalidator_stub,
    ), patch(
        "services.traffic.users.service.SubscriptionCacheInvalidator",
        return_value=invalidator_stub,
    ):
        yield


@pytest.fixture()
def async_session():
    return AsyncMock()


@pytest.fixture()
def redis_client():
    mock = MagicMock()
    mock.client = AsyncMock()
    return mock
