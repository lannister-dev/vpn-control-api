from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.vpn.keys.schemas import VpnTransport


def _make_plan(*, traffic_limit_bytes: int = 0):
    return SimpleNamespace(traffic_limit_bytes=traffic_limit_bytes)


def _make_subscription(*, plan=None):
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        plan=plan,
    )


def _make_vpn_key(*, subscription_id=None, traffic_limit_mb: int = 0):
    return SimpleNamespace(
        id=uuid4(),
        subscription_id=subscription_id,
        traffic_limit_mb=traffic_limit_mb,
    )


class TestCreateVpnKeyForTransport:
    """Test that _create_vpn_key_for_transport correctly derives limits from plan."""

    async def test_key_inherits_limit_from_plan(self):
        """Limited plan → key gets traffic_limit_mb from plan bytes."""
        from services.vpn.subscriptions.service import SubscriptionService

        session = AsyncMock()
        svc = SubscriptionService.__new__(SubscriptionService)
        svc.vpn_key_repository = AsyncMock()

        plan = _make_plan(traffic_limit_bytes=10 * 1024 * 1024 * 1024)  # 10 GB
        sub = _make_subscription(plan=plan)

        created_key = _make_vpn_key(subscription_id=sub.id, traffic_limit_mb=10240)
        svc.vpn_key_repository.create.return_value = created_key

        result = await svc._create_vpn_key_for_transport(
            subscription=sub,
            transport=VpnTransport.ws,
            valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )

        call_args = svc.vpn_key_repository.create.call_args[0][0]
        # 10 GB / 1MB = 10240 MB
        assert call_args["traffic_limit_mb"] == 10240
        assert call_args["subscription_id"] == sub.id

    async def test_key_unlimited_when_plan_unlimited(self):
        """Unlimited plan (traffic_limit_bytes=0) → key gets traffic_limit_mb=0."""
        from services.vpn.subscriptions.service import SubscriptionService

        svc = SubscriptionService.__new__(SubscriptionService)
        svc.vpn_key_repository = AsyncMock()

        plan = _make_plan(traffic_limit_bytes=0)
        sub = _make_subscription(plan=plan)
        svc.vpn_key_repository.create.return_value = _make_vpn_key()

        await svc._create_vpn_key_for_transport(
            subscription=sub,
            transport=VpnTransport.reality,
            valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )

        call_args = svc.vpn_key_repository.create.call_args[0][0]
        assert call_args["traffic_limit_mb"] == 0

    async def test_key_unlimited_when_no_plan(self):
        """No plan → key gets traffic_limit_mb=0."""
        from services.vpn.subscriptions.service import SubscriptionService

        svc = SubscriptionService.__new__(SubscriptionService)
        svc.vpn_key_repository = AsyncMock()

        sub = _make_subscription(plan=None)
        svc.vpn_key_repository.create.return_value = _make_vpn_key()

        await svc._create_vpn_key_for_transport(
            subscription=sub,
            transport=VpnTransport.xhttp,
            valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )

        call_args = svc.vpn_key_repository.create.call_args[0][0]
        assert call_args["traffic_limit_mb"] == 0
        assert call_args["subscription_id"] == sub.id
