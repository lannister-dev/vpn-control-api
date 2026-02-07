from __future__ import annotations

import hashlib
import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.artifacts.service import ProfileArtifactService
from services.artifacts.exceptions import ArtifactStoreError
from services.artifacts.schemas import ProfileArtifactPublishIn


VALID_ARTIFACT = {
    "ws_tls_v1": {
        "type": "ws_tls",
        "display_name": "CDN WS TLS",
        "client": {"path": "/ws", "host": "cdn.example.com", "sni": "cdn.example.com"},
    }
}


@pytest.fixture()
def service(async_session):
    svc = ProfileArtifactService(async_session)
    svc.repository = AsyncMock()
    return svc


class TestPublish:
    async def test_version_increments(self, service):
        service.repository.get_latest_version.return_value = 3
        service.repository.create.return_value = MagicMock(
            id="fake", version=4, checksum="abc"
        )

        data = ProfileArtifactPublishIn(artifact=VALID_ARTIFACT)
        result = await service.publish(data)

        service.repository.deactivate_all.assert_awaited_once()
        call_args = service.repository.create.call_args[0][0]
        assert call_args["version"] == 4

    async def test_checksum_computed(self, service):
        service.repository.get_latest_version.return_value = 0
        service.repository.create.return_value = MagicMock()

        data = ProfileArtifactPublishIn(artifact=VALID_ARTIFACT)
        await service.publish(data)

        call_args = service.repository.create.call_args[0][0]
        expected = hashlib.sha256(
            json.dumps(VALID_ARTIFACT, sort_keys=True).encode()
        ).hexdigest()
        assert call_args["checksum"] == expected

    async def test_first_version_is_1(self, service):
        service.repository.get_latest_version.return_value = 0
        service.repository.create.return_value = MagicMock()

        data = ProfileArtifactPublishIn(artifact=VALID_ARTIFACT)
        await service.publish(data)

        call_args = service.repository.create.call_args[0][0]
        assert call_args["version"] == 1


class TestGetActive:
    async def test_no_active_raises(self, service):
        service.repository.get_active.return_value = None
        with pytest.raises(ArtifactStoreError, match="No active"):
            await service.get_active()

    async def test_returns_artifact(self, service):
        expected = MagicMock()
        service.repository.get_active.return_value = expected
        result = await service.get_active()
        assert result is expected
