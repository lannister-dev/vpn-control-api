from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.artifacts.service import ProfileArtifactService
from services.artifacts.schemas import ArtifactRoutesBootstrapIn


def _backend_node(*, name: str):
    node = MagicMock()
    node.id = uuid4()
    node.name = name
    node.role = "backend"
    node.is_active = True
    node.is_enabled = True
    node.is_draining = False
    return node


def _transport_profile(*, name: str, is_active: bool, port: int):
    profile = MagicMock()
    profile.id = uuid4()
    profile.name = name
    profile.protocol = "vless"
    profile.network = "tcp"
    profile.security = "reality"
    profile.flow = "xtls-rprx-vision"
    profile.reality_public_key = "PUB"
    profile.reality_short_id = "abcd1234"
    profile.reality_server_name = "www.google.com"
    profile.tls_fingerprint = "chrome"
    profile.grpc_service_name = None
    profile.port = port
    profile.is_active = is_active
    return profile


def _route(*, name: str, node_id, transport_profile_id, is_active: bool):
    route = MagicMock()
    route.id = uuid4()
    route.name = name
    route.node_id = node_id
    route.transport_profile_id = transport_profile_id
    route.base_weight = 50
    route.effective_weight = 50
    route.health_status = "healthy"
    route.is_active = is_active
    return route


def _artifact_profile_reality() -> dict:
    return {
        "type": "reality_tcp",
        "display_name": "Reality Google",
        "client": {
            "sni": "www.google.com",
            "flow": "xtls-rprx-vision",
            "fingerprint": "chrome",
            "public_key": "PUBLIC_KEY_1234567890",
            "short_id": "abcd1234",
        },
    }


@pytest.mark.asyncio
async def test_bootstrap_from_artifact_dry_run_counts_without_writes(async_session):
    service = ProfileArtifactService(async_session)
    service.repository = AsyncMock()
    service.node_repository = AsyncMock()
    service.transport_repository = AsyncMock()
    service.route_repository = AsyncMock()

    artifact = {
        "reality-google": _artifact_profile_reality(),
        "ws-backup": {
            "type": "ws_tls",
            "display_name": "WS Backup",
            "client": {"path": "/ws", "host": "cdn.example.com", "sni": "cdn.example.com"},
        },
    }
    service.repository.get_active.return_value = MagicMock(
        version=7,
        artifact=artifact,
    )

    node_1 = _backend_node(name="be-1")
    node_2 = _backend_node(name="be-2")
    service.node_repository.list_public.return_value = [node_1, node_2]
    service.transport_repository.list_by_names.return_value = []
    service.route_repository.list_by_names.return_value = []

    out = await service.bootstrap_routes_from_active_artifact(
        ArtifactRoutesBootstrapIn(
            dry_run=True,
            include_ws_tls=False,
        )
    )

    assert out.dry_run is True
    assert out.profiles_total == 2
    assert out.profiles_selected == 1
    assert out.routes_total == 2
    assert out.transport_profiles_created == 1
    assert out.routes_created == 2
    assert any("ws-backup" in item for item in out.skipped_profiles)
    service.transport_repository.create.assert_not_awaited()
    service.route_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_bootstrap_updates_inactive_transport_and_route(async_session):
    service = ProfileArtifactService(async_session)
    service.repository = AsyncMock()
    service.node_repository = AsyncMock()
    service.transport_repository = AsyncMock()
    service.route_repository = AsyncMock()

    artifact = {"reality-google": _artifact_profile_reality()}
    service.repository.get_active.return_value = MagicMock(
        version=11,
        artifact=artifact,
    )

    backend = _backend_node(name="be-main")
    service.node_repository.list_public.return_value = [backend]

    transport_name = "reality-google"
    existing_transport = _transport_profile(name=transport_name, is_active=False, port=2053)
    service.transport_repository.list_by_names.return_value = [existing_transport]
    service.transport_repository.update_by_id = AsyncMock(return_value=existing_transport)

    route_name = "auto-be-main-reality-google"
    existing_route = _route(
        name=route_name,
        node_id=backend.id,
        transport_profile_id=existing_transport.id,
        is_active=False,
    )
    service.route_repository.list_by_names.return_value = [existing_route]
    service.route_repository.update_by_id = AsyncMock(return_value=existing_route)

    out = await service.bootstrap_routes_from_active_artifact(
        ArtifactRoutesBootstrapIn(
            dry_run=False,
            include_ws_tls=False,
            default_reality_port=443,
        )
    )

    assert out.transport_profiles_created == 0
    assert out.transport_profiles_updated == 1
    assert out.transport_profiles_reactivated == 1
    assert out.routes_total == 1
    assert out.routes_created == 0
    assert out.routes_updated == 1
    assert out.routes_reactivated == 1
    service.transport_repository.update_by_id.assert_awaited_once()
    service.route_repository.update_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_raises_when_no_eligible_profiles(async_session):
    service = ProfileArtifactService(async_session)
    service.repository = AsyncMock()
    service.node_repository = AsyncMock()
    service.transport_repository = AsyncMock()
    service.route_repository = AsyncMock()

    artifact = {
        "ws-only": {
            "type": "ws_tls",
            "display_name": "WS Only",
            "client": {"path": "/ws", "host": "cdn.example.com", "sni": "cdn.example.com"},
        }
    }
    service.repository.get_active.return_value = MagicMock(
        version=3,
        artifact=artifact,
    )

    with pytest.raises(HTTPException) as exc:
        await service.bootstrap_routes_from_active_artifact(
            ArtifactRoutesBootstrapIn(include_ws_tls=False)
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_bootstrap_raises_when_matrix_expectation_mismatch(async_session):
    service = ProfileArtifactService(async_session)
    service.repository = AsyncMock()
    service.node_repository = AsyncMock()
    service.transport_repository = AsyncMock()
    service.route_repository = AsyncMock()

    artifact = {"reality-google": _artifact_profile_reality()}
    service.repository.get_active.return_value = MagicMock(
        version=13,
        artifact=artifact,
    )

    backend = _backend_node(name="be-main")
    service.node_repository.list_public.return_value = [backend]
    service.transport_repository.list_by_names.return_value = []
    service.route_repository.list_by_names.return_value = []

    with pytest.raises(HTTPException) as exc:
        await service.bootstrap_routes_from_active_artifact(
            ArtifactRoutesBootstrapIn(
                include_ws_tls=False,
                expected_profiles_selected=2,
            )
        )

    assert exc.value.status_code == 409
    assert "expected_profiles_selected=2" in str(exc.value.detail)
