from __future__ import annotations

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
