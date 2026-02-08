from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from fastapi import HTTPException

from services.vpn.keys.schemas import VpnKeyCreate, VpnProtocol, VpnTransport, KeyAssignmentCreate, AssignmentDesiredState
from services.vpn.keys.service import VpnKeyService
from datetime import datetime, timezone


@pytest.fixture()
def service(async_session):
    svc = VpnKeyService(async_session)
    svc.key_repository = AsyncMock()
    svc.user_repository = AsyncMock()
    svc.assignment_repository = AsyncMock()
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
    async def test_key_not_found_raises_404(self, service):
        service.key_repository.get_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await service.assign_key(
                uuid4(),
                KeyAssignmentCreate(node_id=uuid4(), desired_state=AssignmentDesiredState.present),
            )
        assert exc_info.value.status_code == 404

    async def test_revoked_key_raises_409(self, service):
        key = MagicMock(is_revoked=True)
        service.key_repository.get_by_id.return_value = key
        with pytest.raises(HTTPException) as exc_info:
            await service.assign_key(
                uuid4(),
                KeyAssignmentCreate(node_id=uuid4(), desired_state=AssignmentDesiredState.present),
            )
        assert exc_info.value.status_code == 409

    async def test_success(self, service):
        key = MagicMock(is_revoked=False)
        service.key_repository.get_by_id.return_value = key
        await service.assign_key(
            uuid4(),
            KeyAssignmentCreate(node_id=uuid4(), desired_state=AssignmentDesiredState.present),
        )
        service.assignment_repository.upsert_assignment_set_pending.assert_awaited_once()


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
        service.assignment_repository.revoke_all_for_key.assert_not_awaited()

    async def test_success(self, service):
        key = MagicMock(is_revoked=False)
        service.key_repository.get_by_id.return_value = key
        key_id = uuid4()
        await service.revoke_key(key_id)
        assert key.is_revoked is True
        service.assignment_repository.revoke_all_for_key.assert_awaited_once_with(key_id=key_id)
