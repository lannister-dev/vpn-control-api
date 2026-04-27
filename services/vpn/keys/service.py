from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.keys.schemas import (
    VpnKeyCreate,
    VpnKeyInternalCreate,
)
from services.vpn.subscriptions.cache import SubscriptionCacheInvalidator
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import KEYS_CREATED_TOTAL, VPN_KEY_OPERATION_TOTAL
from shared.redis.client import RedisClient, get_redis_client


class VpnKeyService:
    def __init__(self, session: AsyncSession, redis: RedisClient | None = None):
        self.session = session
        self.key_repository = VpnKeyRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.user_repository = UserRepository(session)
        self.node_agent_transport = NodeAgentPlacementTransport(session)
        self._cache_invalidator = (
            SubscriptionCacheInvalidator(session, redis) if redis is not None else None
        )

    async def create_key(self, payload: VpnKeyCreate):
        user = await self.user_repository.get_by_id(payload.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        internal = VpnKeyInternalCreate(
            **payload.model_dump(),
            client_id=str(uuid4()),
            is_revoked=False,
        )

        result = await self.key_repository.create(internal.model_dump())
        VPN_KEY_OPERATION_TOTAL.labels(operation="created").inc()
        KEYS_CREATED_TOTAL.labels(transport=getattr(payload, "transport", "unknown") or "unknown").inc()
        return result

    async def assign_key(self, _key_id: UUID) -> None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "Legacy key assignment API is disabled. "
                "Use /api/v1/placements for backend placement management."
            ),
        )

    async def revoke_key(self, key_id: UUID) -> None:
        key = await self.key_repository.get_by_id(key_id)
        if not key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
            )
        if key.is_revoked:
            return

        key.is_revoked = True

        await self._set_placement_inactive(key_id=key_id)
        if self._cache_invalidator is not None:
            await self._cache_invalidator.invalidate_by_key_ids([key_id])
        VPN_KEY_OPERATION_TOTAL.labels(operation="revoked").inc()

    async def _set_placement_inactive(self, *, key_id: UUID) -> None:
        await self.placement_repository.set_desired_state_for_key(
            key_id=key_id,
            desired_state=PlacementDesiredState.inactive.value,
            last_migration_reason="key_revoke",
            updated_at=datetime.now(timezone.utc),
        )
        await self.node_agent_transport.enqueue_for_key_state(
            key_id=key_id,
            desired_state=PlacementDesiredState.inactive.value,
        )


def get_vpn_key_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> VpnKeyService:
    return VpnKeyService(session, redis)
