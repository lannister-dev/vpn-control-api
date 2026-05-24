from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.nodes.exceptions import (
    AdminNodeAlreadyBootstrappedError,
    AdminNodeCreateError,
    AdminNodeNotFoundError,
)
from services.nodes.schemas import AdminNodeCreateIn
from services.nodes.service import VpnNodeService


def _make_service(async_session) -> VpnNodeService:
    service = VpnNodeService(async_session)
    service.vpn_node_repository = AsyncMock()
    service.node_agent_state_repository = AsyncMock()
    service.node_agent_identity_repository = AsyncMock()
    return service


def _built_node(**overrides):
    base = dict(
        id=uuid4(),
        name="vpn-yc-entry-42",
        role="entry",
        region="ru-central1-d",
        public_domain="",
        reality_ip=None,
        internal_wg_ip="",
        node_key=None,
        xray_api_port=10085,
        agent_port=9000,
        is_enabled=True,
        is_draining=False,
        is_active=True,
        capacity=100,
        upstream_node_id=None,
        bootstrap_token_expires_at=None,
        bootstrapped_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_admin_create_node_mints_bootstrap_token_and_returns_install_command(
    async_session,
):
    service = _make_service(async_session)
    service.vpn_node_repository.get_one_by = AsyncMock(return_value=None)
    created = _built_node(name="vpn-yc-entry-42", role="entry")
    service.vpn_node_repository.create = AsyncMock(return_value=created)

    payload = AdminNodeCreateIn(
        name="vpn-yc-entry-42",
        role="entry",
        region="ru-central1-d",
        capacity=150,
    )

    out = await service.admin_create_node(payload)

    service.vpn_node_repository.get_one_by.assert_awaited_once_with(name="vpn-yc-entry-42")
    service.vpn_node_repository.create.assert_awaited_once()
    created_kwargs = service.vpn_node_repository.create.await_args.args[0]
    assert created_kwargs["name"] == "vpn-yc-entry-42"
    assert created_kwargs["role"] == "entry"
    assert created_kwargs["bootstrapped_at"] is None
    assert created_kwargs["bootstrap_token_expires_at"] is not None
    assert created_kwargs["auth_token_hash"] and len(created_kwargs["auth_token_hash"]) == 64

    assert out.bootstrap_token
    assert out.bootstrap_token_expires_at > datetime.now(timezone.utc)
    assert out.install_command
    assert out.node.id == created.id


@pytest.mark.asyncio
async def test_admin_create_node_rejects_invalid_role(async_session):
    service = _make_service(async_session)
    service.vpn_node_repository.get_one_by = AsyncMock(return_value=None)

    payload = AdminNodeCreateIn(
        name="x",
        role="not-a-real-role",
        region="ru-central1-d",
    )

    with pytest.raises(AdminNodeCreateError):
        await service.admin_create_node(payload)

    service.vpn_node_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_create_node_rejects_duplicate_name(async_session):
    service = _make_service(async_session)
    service.vpn_node_repository.get_one_by = AsyncMock(return_value=_built_node())

    payload = AdminNodeCreateIn(
        name="vpn-yc-entry-42",
        role="entry",
        region="ru-central1-d",
    )

    with pytest.raises(AdminNodeCreateError):
        await service.admin_create_node(payload)

    service.vpn_node_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_rotate_bootstrap_token_updates_hash_and_expiry(async_session):
    service = _make_service(async_session)
    node = _built_node()
    service.vpn_node_repository.get_by_id = AsyncMock(return_value=node)
    service.vpn_node_repository.update_by_id = AsyncMock()

    out = await service.admin_rotate_bootstrap_token(node.id)

    service.vpn_node_repository.update_by_id.assert_awaited_once()
    update_payload = service.vpn_node_repository.update_by_id.await_args.args[1]
    assert set(update_payload.keys()) == {"auth_token_hash", "bootstrap_token_expires_at"}
    assert len(update_payload["auth_token_hash"]) == 64
    assert update_payload["bootstrap_token_expires_at"] > datetime.now(timezone.utc)

    assert out.node_id == node.id
    assert out.bootstrap_token
    assert out.install_command


@pytest.mark.asyncio
async def test_admin_rotate_bootstrap_token_404_when_missing(async_session):
    service = _make_service(async_session)
    service.vpn_node_repository.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(AdminNodeNotFoundError):
        await service.admin_rotate_bootstrap_token(uuid4())


@pytest.mark.asyncio
async def test_admin_rotate_bootstrap_token_409_when_already_bootstrapped(async_session):
    service = _make_service(async_session)
    node = _built_node(bootstrapped_at=datetime.now(timezone.utc))
    service.vpn_node_repository.get_by_id = AsyncMock(return_value=node)

    with pytest.raises(AdminNodeAlreadyBootstrappedError):
        await service.admin_rotate_bootstrap_token(node.id)


@pytest.mark.asyncio
async def test_mark_bootstrapped_clears_expiry_and_stamps_timestamp(async_session):
    service = _make_service(async_session)
    service.vpn_node_repository.update_by_id = AsyncMock()
    node = _built_node()

    now = await service.mark_bootstrapped(node)

    service.vpn_node_repository.update_by_id.assert_awaited_once()
    update_payload = service.vpn_node_repository.update_by_id.await_args.args[1]
    assert update_payload["bootstrapped_at"] == now
    assert update_payload["bootstrap_token_expires_at"] is None
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
