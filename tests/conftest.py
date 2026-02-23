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

import pytest
from unittest.mock import AsyncMock, MagicMock

from shared.profiles.registry import ProfileRegistry


@pytest.fixture(autouse=True)
def _reset_profile_registry():
    """Reset the global ProfileRegistry before each test."""
    ProfileRegistry.reset()
    yield
    ProfileRegistry.reset()


@pytest.fixture()
def async_session():
    return AsyncMock()


@pytest.fixture()
def redis_client():
    mock = MagicMock()
    mock.client = AsyncMock()
    return mock
