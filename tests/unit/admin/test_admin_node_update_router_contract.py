from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.nodes.router import update_node_by_id, update_node_by_key
from services.nodes.schemas import AdminNodeUpdateIn


def _make_node(**overrides):
    defaults = dict(
        id=uuid4(),
        name="be1",
        region="de",
        public_domain="be1.example.com",
        reality_ip=None,
        internal_wg_ip="10.10.0.1",
        node_key="swarm-node-be1",
        xray_api_port=10085,
        agent_port=9000,
        is_enabled=True,
        is_draining=False,
        capacity=100,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_service(*, get_by_id_return=None, get_by_node_key_return=None, update_return=None):
    repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=get_by_id_return),
        get_by_node_key=AsyncMock(return_value=get_by_node_key_return),
        update_by_id=AsyncMock(return_value=update_return),
    )
    return SimpleNamespace(vpn_node_repository=repo)


# ── PATCH /agent/nodes/{node_id} ──────────────────────────────


@pytest.mark.asyncio
async def test_update_node_by_id_updates_reality_ip():
    node = _make_node()
    updated = _make_node(id=node.id, reality_ip="1.2.3.4")
    service = _make_service(get_by_id_return=node, update_return=updated)

    result = await update_node_by_id(
        node_id=node.id,
        payload=AdminNodeUpdateIn(reality_ip="1.2.3.4"),
        service=service,
    )

    assert result.reality_ip == "1.2.3.4"
    service.vpn_node_repository.get_by_id.assert_awaited_once_with(node.id)
    service.vpn_node_repository.update_by_id.assert_awaited_once_with(
        node.id, {"reality_ip": "1.2.3.4"}
    )


@pytest.mark.asyncio
async def test_update_node_by_id_multiple_fields():
    node = _make_node()
    updated = _make_node(id=node.id, region="nl", capacity=200)
    service = _make_service(get_by_id_return=node, update_return=updated)

    result = await update_node_by_id(
        node_id=node.id,
        payload=AdminNodeUpdateIn(region="nl", capacity=200),
        service=service,
    )

    assert result.region == "nl"
    assert result.capacity == 200
    call_data = service.vpn_node_repository.update_by_id.await_args.args[1]
    assert call_data == {"region": "nl", "capacity": 200}


@pytest.mark.asyncio
async def test_update_node_by_id_not_found():
    service = _make_service(get_by_id_return=None)

    with pytest.raises(HTTPException) as exc_info:
        await update_node_by_id(
            node_id=uuid4(),
            payload=AdminNodeUpdateIn(region="fi"),
            service=service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_node_by_id_empty_payload():
    service = _make_service()

    with pytest.raises(HTTPException) as exc_info:
        await update_node_by_id(
            node_id=uuid4(),
            payload=AdminNodeUpdateIn(),
            service=service,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Empty payload"
    service.vpn_node_repository.get_by_id.assert_not_awaited()


# ── PATCH /agent/nodes/by-key/{node_key} ─────────────────────


@pytest.mark.asyncio
async def test_update_node_by_key_updates_region():
    node = _make_node(node_key="swarm-node-be1")
    updated = _make_node(id=node.id, region="fi")
    service = _make_service(get_by_node_key_return=node, update_return=updated)

    result = await update_node_by_key(
        node_key="swarm-node-be1",
        payload=AdminNodeUpdateIn(region="fi"),
        service=service,
    )

    assert result.region == "fi"
    service.vpn_node_repository.get_by_node_key.assert_awaited_once_with("swarm-node-be1")
    service.vpn_node_repository.update_by_id.assert_awaited_once_with(
        node.id, {"region": "fi"}
    )


@pytest.mark.asyncio
async def test_update_node_by_key_not_found():
    service = _make_service(get_by_node_key_return=None)

    with pytest.raises(HTTPException) as exc_info:
        await update_node_by_key(
            node_key="nonexistent",
            payload=AdminNodeUpdateIn(reality_ip="5.6.7.8"),
            service=service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_node_by_key_empty_payload():
    service = _make_service()

    with pytest.raises(HTTPException) as exc_info:
        await update_node_by_key(
            node_key="swarm-node-be1",
            payload=AdminNodeUpdateIn(),
            service=service,
        )

    assert exc_info.value.status_code == 422
    service.vpn_node_repository.get_by_node_key.assert_not_awaited()


# ── Schema validation ────────────────────────────────────────


def test_admin_node_update_forbids_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AdminNodeUpdateIn(auth_token_hash="secret")


def test_admin_node_update_capacity_bounds():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AdminNodeUpdateIn(capacity=0)

    with pytest.raises(ValidationError):
        AdminNodeUpdateIn(capacity=10001)

    valid = AdminNodeUpdateIn(capacity=500)
    assert valid.capacity == 500


def test_admin_node_update_excludes_unset():
    payload = AdminNodeUpdateIn(reality_ip="1.2.3.4")
    data = payload.model_dump(exclude_unset=True)
    assert data == {"reality_ip": "1.2.3.4"}
    assert "region" not in data
    assert "capacity" not in data
