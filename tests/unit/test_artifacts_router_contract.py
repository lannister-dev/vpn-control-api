from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.artifacts.exceptions import ArtifactStoreError
from services.artifacts.router import bootstrap_routes_from_active_profiles_artifact
from services.artifacts.schemas import ArtifactRoutesBootstrapIn, ArtifactRoutesBootstrapOut


@pytest.mark.asyncio
async def test_bootstrap_routes_from_active_profiles_artifact_contract():
    payload = ArtifactRoutesBootstrapIn(
        dry_run=True,
        include_ws_tls=False,
    )
    expected = ArtifactRoutesBootstrapOut(
        artifact_version=5,
        dry_run=True,
        backends_selected=2,
        profiles_total=3,
        profiles_selected=2,
        routes_total=4,
        transport_profiles_created=2,
        transport_profiles_updated=0,
        transport_profiles_reactivated=0,
        routes_created=4,
        routes_updated=0,
        routes_reactivated=0,
        skipped_profiles=["ws-fallback: skipped by include_ws_tls=false"],
    )

    service = SimpleNamespace(
        bootstrap_routes_from_active_artifact=AsyncMock(return_value=expected),
    )

    out = await bootstrap_routes_from_active_profiles_artifact(payload=payload, service=service)

    assert out == expected
    service.bootstrap_routes_from_active_artifact.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_bootstrap_routes_from_active_profiles_artifact_404_on_missing_artifact():
    payload = ArtifactRoutesBootstrapIn()
    service = SimpleNamespace(
        bootstrap_routes_from_active_artifact=AsyncMock(side_effect=ArtifactStoreError("No active profiles artifact")),
    )

    with pytest.raises(HTTPException) as exc:
        await bootstrap_routes_from_active_profiles_artifact(payload=payload, service=service)

    assert exc.value.status_code == 404
    assert "No active profiles artifact" in str(exc.value.detail)
