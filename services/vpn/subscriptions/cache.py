from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.vpn.keys.models import VpnKey
from services.vpn.subscriptions import redis_key
from services.vpn.subscriptions.model import Subscription
from shared.redis.client import RedisClient
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("subscription-cache"))


class SubscriptionCacheInvalidator:
    def __init__(self, session: AsyncSession, redis: RedisClient):
        self.session = session
        self.redis = redis

    async def invalidate_by_token_hashes(self, token_hashes: list[str]) -> int:
        if not token_hashes:
            return 0
        deleted = 0
        for token_hash in token_hashes:
            if not token_hash:
                continue
            deleted += await self._invalidate_one(token_hash)
        return deleted

    async def invalidate_by_subscription_ids(self, subscription_ids: list[UUID]) -> int:
        if not subscription_ids:
            return 0
        rows = await self.session.execute(
            select(Subscription.token_hash, Subscription.prev_token_hash).where(
                Subscription.id.in_(subscription_ids)
            )
        )
        token_hashes: list[str] = []
        for token_hash, prev_token_hash in rows.all():
            if token_hash:
                token_hashes.append(token_hash)
            if prev_token_hash:
                token_hashes.append(prev_token_hash)
        return await self.invalidate_by_token_hashes(token_hashes)

    async def invalidate_by_key_ids(self, key_ids: list[UUID]) -> int:
        if not key_ids:
            return 0
        rows = await self.session.execute(
            select(VpnKey.subscription_id)
            .where(VpnKey.id.in_(key_ids))
            .where(VpnKey.subscription_id.is_not(None))
        )
        subscription_ids = list({row[0] for row in rows.all() if row[0] is not None})
        return await self.invalidate_by_subscription_ids(subscription_ids)

    async def _invalidate_one(self, token_hash: str) -> int:
        index_key = redis_key.payload_cache_index(token_hash=token_hash)
        try:
            keys = await self.redis.client.smembers(index_key)
            keys_to_delete = [
                key for key in keys
                if isinstance(key, str) and redis_key.is_payload_cache_key(key)
            ]
            count = 0
            if keys_to_delete:
                await self.redis.client.delete(*keys_to_delete)
                count = len(keys_to_delete)
            await self.redis.client.delete(index_key)
            return count
        except Exception:
            logger.warning("subscription_cache_invalidate_failed", token_hash=token_hash[:8])
            return 0
