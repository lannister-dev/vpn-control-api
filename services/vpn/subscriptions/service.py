from __future__ import annotations

import hashlib
import time
from datetime import timezone, datetime, timedelta
from typing import Iterable
from uuid import uuid4, UUID

from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.repository import VpnNodeRepository
from services.users.repository import UserRepository
from services.vpn.subscriptions.constants import RATE_LIMIT_WINDOW_SEC, RATE_LIMIT_REQUESTS
from services.vpn.subscriptions.repository import SubscriptionRepository
from services.vpn.subscriptions.utils import SubscriptionUtils
from shared.database.session import AsyncDatabase
from shared.profiles.builder import VlessUriBuilder
from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.registry import ProfileRegistry
from shared.profiles.schemas import NodePublic, RealityTcpProfile, WsTlsProfile
from shared.metrics import SUBSCRIPTION_BUILD_DURATION
from shared.redis.client import RedisClient, get_redis_client

from services.vpn.subscriptions.schemas import (
    SubscriptionCreateIn,
    SubscriptionCreatedOut,
    SubscriptionRotateOut, SubscriptionInternalUpdate,
)
from services.vpn.subscriptions.schemas import (
    SubscriptionInternalCreate,
    SubscriptionInternalRotate,
)
from services.vpn.subscriptions.exceptions import (
    SubscriptionNotFound,
    SubscriptionInactive,
    SubscriptionExpired,
    SubscriptionTokenExpired,
    SubscriptionBuild,
    SubscriptionRateLimited,
)


class SubscriptionService:
    def __init__(self, session: AsyncSession, redis: RedisClient):
        self.session = session
        self.redis = redis
        self.subscription_repository = SubscriptionRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.user_repository = UserRepository(session)

    async def create(self, data: SubscriptionCreateIn) -> SubscriptionCreatedOut:
        user = await self.user_repository.get_by_id(data.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        raw_token = SubscriptionUtils.generate()
        token_hash = SubscriptionUtils.hash(raw_token)

        data = SubscriptionInternalCreate(
            user_id=data.user_id,
            client_id=uuid4(),
            token_hash=token_hash,
            is_active=True,
            expires_at=data.expires_at,
            profile_key=data.profile_key,
            preferred_region=data.preferred_region,
        )
        subscription = await self.subscription_repository.create(
            data.model_dump()
        )
        return SubscriptionCreatedOut(
            id=subscription.id,
            client_id=subscription.client_id,
            token=raw_token,
            expires_at=subscription.expires_at,
            is_active=subscription.is_active,
        )

    async def rotate_token(
            self,
            subscription_id: UUID,
            *,
            grace_seconds: int = 3600,
    ) -> SubscriptionRotateOut:
        sub = await self.subscription_repository.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound

        new_raw = SubscriptionUtils.generate()
        new_hash = SubscriptionUtils.hash(new_raw)

        now = datetime.now(timezone.utc)

        data = SubscriptionInternalRotate(
            token_hash=new_hash,
            prev_token_hash=sub.token_hash,
            prev_token_expires_at=now + timedelta(seconds=grace_seconds),
            updated_at=now,
        )

        updated = await self.subscription_repository.update_by_id(
            subscription_id, data.model_dump()
        )
        if not updated:
            raise SubscriptionNotFound

        await self._invalidate_rate_limit(sub.token_hash)
        await self._invalidate_rate_limit(new_hash)

        return SubscriptionRotateOut(token=new_raw)

    # ------------------------------------------------------------------
    # ACTIVATE / DEACTIVATE
    # ------------------------------------------------------------------

    async def deactivate(self, subscription_id: UUID) -> bool:
        subscription = await self.subscription_repository.get_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFound(subscription_id)

        data = SubscriptionInternalUpdate(
            is_active=False,
            updated_at=datetime.now(timezone.utc)
        )
        await self.subscription_repository.update_by_id(
            item_id=subscription.id, data=data.model_dump()
        )
        return True

    async def activate(self, subscription_id: UUID) -> bool:
        subscription = await self.subscription_repository.get_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFound(subscription_id)

        data = SubscriptionInternalUpdate(
            is_active = True,
            updated_at = datetime.now(timezone.utc)
        )
        await self.subscription_repository.update_by_id(
            item_id=subscription.id, data=data.model_dump()
        )
        return True


    async def build_payload(
            self,
            raw_token: str,
            *,
            if_none_match: str | None = None,
    ) -> tuple[str, str, bool]:
        t0 = time.perf_counter()

        token_hash = SubscriptionUtils.hash(raw_token)

        await self._enforce_rate_limit(token_hash)

        subscription = await self.subscription_repository.get_by_any_token_hash(token_hash)
        if not subscription:
            raise SubscriptionNotFound("subscription")

        self._validate_subscription(subscription, token_hash)

        nodes = await self.node_repository.list_public(
            preferred_region=subscription.preferred_region
        )
        profiles = self._select_profiles(subscription.profile_key)

        uris = self._build_uris(
            client_id=str(subscription.client_id),
            nodes=nodes,
            profiles=profiles,
        )

        if not uris:
            raise SubscriptionBuild("No available configs")

        payload = "\n".join(uris)
        etag = self._calc_etag(subscription, nodes, profiles)

        SUBSCRIPTION_BUILD_DURATION.observe(time.perf_counter() - t0)

        if if_none_match and if_none_match == etag:
            return "", etag, True

        return payload, etag, False

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _validate_subscription(self, sub, token_hash: str) -> None:
        now = datetime.now(timezone.utc)

        if not sub.is_active:
            raise SubscriptionInactive()

        if sub.expires_at and sub.expires_at <= now:
            raise SubscriptionExpired()

        if sub.prev_token_hash == token_hash:
            if sub.prev_token_expires_at and sub.prev_token_expires_at <= now:
                raise SubscriptionTokenExpired()

    def _select_profiles(
            self,
            profile_key: str | None,
    ) -> list[WsTlsProfile | RealityTcpProfile]:
        try:
            if profile_key:
                return [ProfileRegistry.get(profile_key).profile]
            return [
                ProfileRegistry.get(k).profile
                for k in ProfileRegistry.all_keys()
            ]
        except ProfileRegistryError as exc:
            raise SubscriptionBuild(str(exc)) from exc

    def _build_uris(
            self,
            *,
            client_id: str,
            nodes: Iterable,
            profiles: Iterable[WsTlsProfile | RealityTcpProfile],
    ) -> list[str]:
        result: list[str] = []

        for node in nodes:
            node_public = NodePublic(
                domain=node.public_domain,
                port=443,
                remark=node.name,
                region=node.region,
            )
            for profile in profiles:
                try:
                    result.append(
                        VlessUriBuilder.build(
                            client_id=client_id,
                            node=node_public,
                            profile=profile,
                        )
                    )
                except Exception:
                    continue

        return result

    def _calc_etag(self, sub, nodes, profiles) -> str:
        base = "|".join([
            str(sub.id),
            sub.updated_at.isoformat(),
            sub.profile_key or "",
            sub.preferred_region or "",
            ",".join(sorted(n.public_domain for n in nodes)),
            ",".join(f"{p.type}:{p.version}" for p in profiles),
        ])
        return hashlib.sha256(base.encode()).hexdigest()

    # ------------------------------------------------------------------
    # RATE LIMIT (REDIS)
    # ------------------------------------------------------------------

    def _rl_key(self, token_hash: str) -> str:
        return f"sub:rl:{token_hash}"

    async def _enforce_rate_limit(self, token_hash: str) -> None:
        key = self._rl_key(token_hash)

        current = await self.redis.client.get(key)
        if current is None:
            await self.redis.client.setex(key, RATE_LIMIT_WINDOW_SEC, 1)
            return

        if int(current) >= RATE_LIMIT_REQUESTS:
            raise SubscriptionRateLimited()

        await self.redis.client.incr(key)

    async def _invalidate_rate_limit(self, token_hash: str) -> None:
        await self.redis.client.delete(self._rl_key(token_hash))

def get_subscription_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> SubscriptionService:
    return SubscriptionService(session, redis)