from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.traffic.users.constants import _MIB, _MIGRATION_REASON
from services.traffic.users.repository import TrafficUsageRepository
from services.traffic.users.schemas import (
    TrafficHistoryItemOut,
    TrafficHistoryListOut,
    TrafficKeySummaryListOut,
    TrafficKeySummaryOut,
    TrafficUsageCreate,
    UserTrafficIn,
    UserTrafficSummaryListOut,
    UserTrafficSummaryOut,
)
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.subscriptions.cache import SubscriptionCacheInvalidator
from services.vpn.subscriptions.repository import SubscriptionRepository
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import VPN_KEY_OPERATION_TOTAL
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger

logger_traffic = StructuredLogger(logging.getLogger("traffic-service"))


class UserTrafficService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.key_repository = VpnKeyRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.traffic_usage_repository = TrafficUsageRepository(session)
        self.subscription_repository = SubscriptionRepository(session)
        self.node_agent_transport = NodeAgentPlacementTransport(session)

    async def ingest_users_traffic(self, items: list[UserTrafficIn]) -> dict[str, int]:
        if not items:
            return {"processed": 0, "revoked": 0}

        keys = await self.key_repository.list_by_client_ids(
            client_ids=[item.identifier for item in items],
            active_only=True,
        )
        if not keys:
            return {"processed": 0, "revoked": 0}

        key_by_client = {key.client_id: key for key in keys}
        now = datetime.now(timezone.utc)
        processed = 0
        revoked = 0
        history_rows: list[TrafficUsageCreate] = []
        subscription_deltas: dict[UUID, int] = defaultdict(int)

        for traffic in items:
            key = key_by_client.get(traffic.identifier)
            if key is None:
                continue

            delta = traffic.delta_bytes
            if delta <= 0:
                continue

            processed += 1
            key.used_traffic_bytes = int(key.used_traffic_bytes or 0) + delta
            key.updated_at = now
            history_rows.append(
                TrafficUsageCreate(
                    key_id=key.id,
                    delta_bytes=delta,
                )
            )

            if key.subscription_id:
                subscription_deltas[key.subscription_id] += delta

        # Phase 2: update subscription counters and check plan limits
        exceeded_sub_ids: set[UUID] = set()
        if subscription_deltas:
            subs = await self.subscription_repository.list_by_ids_with_plan(
                list(subscription_deltas.keys())
            )
            for sub in subs:
                delta = subscription_deltas.get(sub.id, 0)
                if delta <= 0:
                    continue
                sub.used_traffic_bytes = int(sub.used_traffic_bytes or 0) + delta
                sub.lifetime_used_traffic_bytes = int(sub.lifetime_used_traffic_bytes or 0) + delta
                sub.updated_at = now

                if not sub.plan or sub.plan.traffic_limit_bytes <= 0:
                    continue  # unlimited plan — no cap
                if sub.used_traffic_bytes >= sub.plan.traffic_limit_bytes:
                    exceeded_sub_ids.add(sub.id)

            if exceeded_sub_ids:
                cache_invalidator = SubscriptionCacheInvalidator(self.session, redis_client)
                await cache_invalidator.invalidate_by_subscription_ids(list(exceeded_sub_ids))
            for sub_id in exceeded_sub_ids:
                revoked += await self._revoke_subscription_keys(sub_id, now)

        # Phase 3: per-key limit fallback for keys WITHOUT subscription
        for key in key_by_client.values():
            if key.subscription_id:
                continue  # handled at subscription level
            if key.is_revoked:
                continue
            limit_bytes = max(0, int(key.traffic_limit_mb or 0)) * _MIB
            if limit_bytes <= 0:
                continue
            if key.used_traffic_bytes < limit_bytes:
                continue

            key.is_revoked = True
            await self.placement_repository.set_desired_state_for_key(
                key_id=key.id,
                desired_state=PlacementDesiredState.inactive.value,
                last_migration_reason=_MIGRATION_REASON,
                updated_at=now,
            )
            await self.node_agent_transport.enqueue_for_key_state(
                key_id=key.id,
                desired_state=PlacementDesiredState.inactive.value,
            )
            VPN_KEY_OPERATION_TOTAL.labels(operation="auto_revoked_traffic_limit").inc()
            revoked += 1

        if history_rows:
            await self.traffic_usage_repository.bulk_create(history_rows)

        if processed > 0:
            logger_traffic.info(
                "users_traffic_ingested",
                processed=processed,
                revoked=revoked,
            )
        return {"processed": processed, "revoked": revoked}

    async def _revoke_subscription_keys(self, subscription_id: UUID, now: datetime) -> int:
        """Revoke all active keys of a subscription due to plan traffic limit."""
        active_keys = await self.key_repository.list_active_by_subscription_id(subscription_id)
        count = 0
        for key in active_keys:
            if key.is_revoked:
                continue
            key.is_revoked = True
            key.updated_at = now
            await self.placement_repository.set_desired_state_for_key(
                key_id=key.id,
                desired_state=PlacementDesiredState.inactive.value,
                last_migration_reason=_MIGRATION_REASON,
                updated_at=now,
            )
            await self.node_agent_transport.enqueue_for_key_state(
                key_id=key.id,
                desired_state=PlacementDesiredState.inactive.value,
            )
            VPN_KEY_OPERATION_TOTAL.labels(operation="auto_revoked_traffic_limit").inc()
            count += 1
        return count

    async def cleanup_history(self, *, retention_days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(retention_days)))
        return await self.traffic_usage_repository.delete_older_than(cutoff=cutoff)


class TrafficAdminService:
    """Read-only service for admin traffic inspection endpoints."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.key_repository = VpnKeyRepository(session)
        self.traffic_usage_repository = TrafficUsageRepository(session)

    async def list_keys_with_traffic(
        self,
        *,
        user_id: UUID | None = None,
        is_revoked: bool | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TrafficKeySummaryListOut:
        keys, total = await self.key_repository.list_with_traffic_summary(
            user_id=user_id,
            is_revoked=is_revoked,
            search=search,
            limit=limit,
            offset=offset,
        )
        return TrafficKeySummaryListOut(
            items=[TrafficKeySummaryOut.model_validate(k) for k in keys],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def top_users_by_traffic(
        self,
        *,
        period: str,
        limit: int = 10,
    ) -> UserTrafficSummaryListOut:
        window_map = {
            "1h": timedelta(hours=1),
            "24h": timedelta(days=1),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }
        window = window_map.get(period, timedelta(days=1))
        to_ts = datetime.now(timezone.utc)
        from_ts = to_ts - window
        rows = await self.traffic_usage_repository.top_users_by_bytes(
            from_ts=from_ts,
            to_ts=to_ts,
            limit=max(1, min(limit, 100)),
        )
        items = [
            UserTrafficSummaryOut(
                user_id=row[0],
                telegram_id=row[1],
                username=row[2],
                plan_name=row[3],
                bytes=row[4],
                keys=row[5],
            )
            for row in rows
        ]
        return UserTrafficSummaryListOut(period=period, from_ts=from_ts, to_ts=to_ts, items=items)

    async def get_key_traffic_history(
        self,
        *,
        key_id: UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TrafficHistoryListOut:
        rows, total = await self.traffic_usage_repository.list_by_key_id(
            key_id=key_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
        return TrafficHistoryListOut(
            items=[TrafficHistoryItemOut.model_validate(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


def get_traffic_admin_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> TrafficAdminService:
    return TrafficAdminService(session)
