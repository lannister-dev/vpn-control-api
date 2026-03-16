from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException

from services.vpn.keys.schemas import VpnKeyCreate, VpnProtocol, VpnTransport
from services.vpn.keys.service import VpnKeyService
from datetime import datetime, timezone


@pytest.fixture()
def service(async_session):
    svc = VpnKeyService(async_session)
    svc.key_repository = AsyncMock()
    svc.user_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    return svc


class TestCreateKey:
    async def test_user_not_found_raises_404(self, service):
        service.user_repository.get_by_id.return_value = None
        payload = VpnKeyCreate(
            user_id=uuid4(),
            protocol=VpnProtocol.vless,
            transport=VpnTransport.ws,
            valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc),
            traffic_limit_mb=1000,
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.create_key(payload)
        assert exc_info.value.status_code == 404

    async def test_success(self, service):
        service.user_repository.get_by_id.return_value = MagicMock()
        service.key_repository.create.return_value = MagicMock(id=uuid4())

        payload = VpnKeyCreate(
            user_id=uuid4(),
            protocol=VpnProtocol.vless,
            transport=VpnTransport.ws,
            valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc),
            traffic_limit_mb=1000,
        )
        result = await service.create_key(payload)
        service.key_repository.create.assert_awaited_once()
        assert result is not None


class TestAssignKey:
    async def test_assign_disabled_raises_410(self, service):
        with pytest.raises(HTTPException) as exc_info:
            await service.assign_key(uuid4())
        assert exc_info.value.status_code == 410


class TestRevokeKey:
    async def test_key_not_found_raises_404(self, service):
        service.key_repository.get_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await service.revoke_key(uuid4())
        assert exc_info.value.status_code == 404

    async def test_already_revoked_noop(self, service):
        key = MagicMock(is_revoked=True)
        service.key_repository.get_by_id.return_value = key
        await service.revoke_key(uuid4())
        service.placement_repository.set_desired_state_for_key.assert_not_awaited()
        service.node_agent_transport.enqueue_for_key_state.assert_not_awaited()

    async def test_success_with_placement(self, service):
        key = MagicMock(is_revoked=False)
        service.key_repository.get_by_id.return_value = key
        key_id = uuid4()
        await service.revoke_key(key_id)
        assert key.is_revoked is True
        service.placement_repository.set_desired_state_for_key.assert_awaited_once()
        service.node_agent_transport.enqueue_for_key_state.assert_awaited_once_with(
            key_id=key_id,
            desired_state="inactive",
        )

    async def test_success_without_placement(self, service):
        key = MagicMock(is_revoked=False)
        service.key_repository.get_by_id.return_value = key
        key_id = uuid4()
        await service.revoke_key(key_id)
        assert key.is_revoked is True
        service.placement_repository.set_desired_state_for_key.assert_awaited_once()
        service.node_agent_transport.enqueue_for_key_state.assert_awaited_once_with(
            key_id=key_id,
            desired_state="inactive",
        )
