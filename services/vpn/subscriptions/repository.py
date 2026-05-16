from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from services.nodes.models import VpnNode
from services.placements.model import UserPlacement
from services.plans.models import Plan
from services.routes.model import Route, TransportProfile
from services.vpn.keys.models import VpnKey
from services.vpn.subscriptions.exceptions import SubscriptionNotFound
from services.vpn.subscriptions.model import (
    Subscription,
    SubscriptionDevice,
    SubscriptionDeviceKey,
)
from shared.database.base_repository import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, session: AsyncSession):
        super().__init__(Subscription, session)

    async def list_by_ids_with_plan(self, ids: list[UUID]) -> list[Subscription]:
        if not ids:
            return []
        stmt = (
            select(self.model)
            .options(joinedload(self.model.plan))
            .where(self.model.id.in_(ids))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def list_needing_traffic_reset(self, *, strategy: str, reset_before) -> list[Subscription]:
        """Find active subscriptions with given reset strategy whose last reset is before cutoff."""
        stmt = (
            select(self.model)
            .join(Plan, self.model.plan_id == Plan.id)
            .options(joinedload(self.model.plan))
            .where(
                self.model.is_active.is_(True),
                Plan.is_active.is_(True),
                Plan.reset_strategy == strategy,
                Plan.traffic_limit_bytes > 0,
                or_(
                    self.model.last_traffic_reset_at.is_(None),
                    self.model.last_traffic_reset_at < reset_before,
                ),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_by_token_hash(self, token_hash: str) -> Subscription | None:
        stmt = select(self.model).where(self.model.token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_any_token_hash(self, token_hash: str) -> Subscription | None:
        stmt = select(self.model).where(
            or_(
                self.model.token_hash == token_hash,
                self.model.prev_token_hash == token_hash,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_backend_placements(
            self, subscription_id: UUID,
    ) -> list[dict]:
        """Per (device, backend) the user is placed on."""
        stmt = (
            select(
                VpnNode.id.label("backend_id"),
                VpnNode.name.label("backend_name"),
                VpnNode.region.label("backend_region"),
                VpnNode.role.label("backend_role"),
                SubscriptionDeviceKey.transport.label("transport"),
                SubscriptionDevice.id.label("device_id"),
                UserPlacement.applied_state.label("placement_state"),
                UserPlacement.sticky_until.label("sticky_until"),
            )
            .join(SubscriptionDeviceKey, SubscriptionDevice.id == SubscriptionDeviceKey.subscription_device_id)
            .join(VpnKey, VpnKey.id == SubscriptionDeviceKey.vpn_key_id)
            .join(UserPlacement, UserPlacement.key_id == VpnKey.id)
            .join(VpnNode, VpnNode.id == UserPlacement.backend_node_id)
            .where(
                SubscriptionDevice.subscription_id == subscription_id,
                SubscriptionDevice.is_active.is_(True),
                UserPlacement.is_active.is_(True),
            )
            .order_by(VpnNode.region, VpnNode.name)
        )
        rows = (await self.session.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    async def list_entry_routes_for_backends(
            self, backend_ids: list[UUID],
    ) -> list[dict]:
        """Healthy/warming-up routes that point to the given backend nodes,
        joined with the entry node and transport profile. Empty list if no IDs."""
        if not backend_ids:
            return []
        entry_node = aliased(VpnNode)
        stmt = (
            select(
                Route.node_id.label("backend_id"),
                entry_node.id.label("entry_id"),
                entry_node.name.label("entry_name"),
                entry_node.region.label("entry_region"),
                entry_node.role.label("entry_role"),
                TransportProfile.network.label("network"),
                TransportProfile.security.label("security"),
                Route.health_status.label("health"),
                Route.effective_weight.label("weight"),
            )
            .join(entry_node, entry_node.id == Route.entry_node_id)
            .join(TransportProfile, TransportProfile.id == Route.transport_profile_id)
            .where(
                Route.node_id.in_(backend_ids),
                Route.is_active.is_(True),
                Route.health_status.in_(("healthy", "warming_up")),
                entry_node.is_enabled.is_(True),
            )
            .order_by(Route.effective_weight.desc(), entry_node.name)
        )
        rows = (await self.session.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    async def list_by_user_id(
            self,
            user_id: UUID,
            active_only: bool = False,
    ) -> list[Subscription]:
        stmt = select(self.model).where(self.model.user_id == user_id)
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_paginated(
            self,
            *,
            active_only: bool = False,
            plan_id: UUID | None = None,
            limit: int = 50,
            offset: int = 0,
    ) -> tuple[list[Subscription], int]:
        base = select(self.model)
        if active_only:
            base = base.where(self.model.is_active.is_(True))
        if plan_id is not None:
            base = base.where(self.model.plan_id == plan_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = base.options(joinedload(self.model.plan)).order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        items = list(result.scalars().unique().all())
        return items, total

    async def deactivate(self, subscription_id: UUID) -> None:
        sub = await self.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound
        sub.is_active = False
        await self.session.flush()

    async def count_stats(self) -> tuple[int, int, int]:
        active_int = case((self.model.is_active.is_(True), 1), else_=0)
        expired_int = case(
            (
                and_(
                    self.model.is_active.is_(True),
                    self.model.expires_at.isnot(None),
                    self.model.expires_at < func.now(),
                ),
                1,
            ),
            else_=0,
        )
        stmt = select(
            func.count().label("total"),
            func.coalesce(func.sum(active_int), 0).label("active"),
            func.coalesce(func.sum(expired_int), 0).label("expired"),
        ).select_from(self.model)
        row = (await self.session.execute(stmt)).one()
        return int(row.total), int(row.active), int(row.expired)

    async def count_stats_at(self, ts: datetime) -> tuple[int, int, int]:
        """Same counts as count_stats(), but as of timestamp `ts`."""
        existed = self.model.created_at <= ts
        active_int = case(
            (
                and_(
                    existed,
                    self.model.is_active.is_(True),
                    or_(self.model.expires_at.is_(None), self.model.expires_at > ts),
                ),
                1,
            ),
            else_=0,
        )
        expired_int = case(
            (
                and_(
                    existed,
                    self.model.is_active.is_(True),
                    self.model.expires_at.isnot(None),
                    self.model.expires_at < ts,
                ),
                1,
            ),
            else_=0,
        )
        total_int = case((existed, 1), else_=0)
        stmt = select(
            func.coalesce(func.sum(total_int), 0).label("total"),
            func.coalesce(func.sum(active_int), 0).label("active"),
            func.coalesce(func.sum(expired_int), 0).label("expired"),
        ).select_from(self.model)
        row = (await self.session.execute(stmt)).one()
        return int(row.total), int(row.active), int(row.expired)

    async def bulk_set_traffic_warning_threshold(
        self, pairs: list[tuple[UUID, int]],
    ) -> int:
        """Single UPDATE for many (subscription_id, threshold_pct) pairs.

        Only raises the watermark — never lowers it.
        Returns affected row count.
        """
        if not pairs:
            return 0
        stmt = text(
            """
            UPDATE subscription AS s
            SET traffic_warning_threshold_pct = v.threshold_pct
            FROM (
                SELECT unnest(CAST(:ids AS uuid[])) AS id,
                       unnest(CAST(:pcts AS int[])) AS threshold_pct
            ) AS v
            WHERE s.id = v.id
              AND v.threshold_pct > COALESCE(s.traffic_warning_threshold_pct, 0)
            """
        )
        ids = [str(p[0]) for p in pairs]
        pcts = [int(p[1]) for p in pairs]
        result = await self.session.execute(stmt, {"ids": ids, "pcts": pcts})
        rowcount = result.rowcount
        if callable(rowcount):
            rowcount = rowcount()
        return int(rowcount or 0)

    async def traffic_check_by_telegram_ids(
        self, telegram_ids: list[int],
    ) -> list[tuple[int, UUID | None, int, int, int]]:
        """Core single-shot batch fetch for bot traffic-warning scheduler.

        Returns (telegram_id, subscription_id, traffic_limit_bytes,
        used_traffic_bytes, traffic_warning_threshold_pct) per input id.
        Users without a subscription get (tid, None, 0, 0, 0).
        Uses LATERAL → one row per user, no ORM hydration.
        """
        if not telegram_ids:
            return []
        stmt = text(
            """
            SELECT
                u.telegram_id,
                s.id                                          AS subscription_id,
                COALESCE(p.traffic_limit_bytes, 0)            AS lim,
                COALESCE(s.used_traffic_bytes, 0)             AS used,
                COALESCE(s.traffic_warning_threshold_pct, 0)  AS warned
            FROM "user" u
            LEFT JOIN LATERAL (
                SELECT id, plan_id, used_traffic_bytes, traffic_warning_threshold_pct
                FROM subscription
                WHERE user_id = u.id AND expires_at IS NOT NULL
                ORDER BY expires_at DESC
                LIMIT 1
            ) s ON TRUE
            LEFT JOIN plan p ON p.id = s.plan_id
            WHERE u.telegram_id = ANY(:tids)
            """
        )
        result = await self.session.execute(stmt, {"tids": telegram_ids})
        return [
            (int(r.telegram_id), r.subscription_id, int(r.lim), int(r.used), int(r.warned))
            for r in result
        ]

    async def get_latest_for_user(self, user_id: UUID) -> Subscription | None:
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.expires_at.is_not(None),
            )
            .order_by(self.model.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_active_subscription(self, user_id: UUID, plan_id: UUID):
        result = await self.session.execute(
            select(self.model).where(
                self.model.user_id == user_id,
                self.model.plan_id == plan_id,
                self.model.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_expired_active(self, *, now, limit: int = 200) -> list[Subscription]:
        stmt = (
            select(self.model)
            .where(
                self.model.is_active.is_(True),
                self.model.expires_at.isnot(None),
                self.model.expires_at < now,
            )
            .order_by(self.model.expires_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_deactivate(self, subscription_ids: list[UUID]) -> int:
        if not subscription_ids:
            return 0
        await self.session.execute(
            update(self.model)
            .where(self.model.id.in_(subscription_ids))
            .values(is_active=False)
        )
        return len(subscription_ids)


class SubscriptionDeviceRepository(BaseRepository[SubscriptionDevice]):
    def __init__(self, session: AsyncSession):
        super().__init__(SubscriptionDevice, session)

    async def get_active_by_sub_and_hwid_hash(
            self,
            *,
            subscription_id: UUID,
            hwid_hash: str,
    ) -> SubscriptionDevice | None:
        res = await self.session.execute(
            select(self.model).where(
                self.model.subscription_id == subscription_id,
                self.model.hwid_hash == hwid_hash,
                self.model.is_active.is_(True),
            )
        )
        return res.scalar_one_or_none()

    async def count_active_for_subscription(self, subscription_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.subscription_id == subscription_id,
                self.model.is_active.is_(True),
            )
        )
        return int(res.scalar_one())

    async def count_active_by_subscription_ids(
            self, subscription_ids: list[UUID],
    ) -> dict[UUID, int]:
        if not subscription_ids:
            return {}
        ids = list(dict.fromkeys(subscription_ids))
        stmt = (
            select(self.model.subscription_id, func.count(self.model.id))
            .where(
                self.model.subscription_id.in_(ids),
                self.model.is_active.is_(True),
            )
            .group_by(self.model.subscription_id)
        )
        res = await self.session.execute(stmt)
        counts = {row[0]: int(row[1]) for row in res.all()}
        for sub_id in ids:
            counts.setdefault(sub_id, 0)
        return counts

    async def list_by_subscription(
            self,
            subscription_id: UUID,
            *,
            active_only: bool = False,
    ) -> list[SubscriptionDevice]:
        stmt = select(self.model).where(
            self.model.subscription_id == subscription_id,
        )
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        stmt = stmt.order_by(self.model.created_at.desc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_by_id_for_subscription(
            self,
            *,
            subscription_id: UUID,
            device_id: UUID,
    ) -> SubscriptionDevice | None:
        res = await self.session.execute(
            select(self.model).where(
                self.model.id == device_id,
                self.model.subscription_id == subscription_id,
            )
        )
        return res.scalar_one_or_none()

    async def list_key_ids_for_subscription(
            self,
            subscription_id: UUID,
            *,
            active_only: bool = False,
    ) -> list[UUID]:
        bundle_stmt = (
            select(SubscriptionDeviceKey.vpn_key_id)
            .join(
                self.model,
                SubscriptionDeviceKey.subscription_device_id == self.model.id,
            )
            .where(self.model.subscription_id == subscription_id)
        )
        if active_only:
            bundle_stmt = bundle_stmt.where(
                self.model.is_active.is_(True),
                SubscriptionDeviceKey.is_active.is_(True),
            )
        bundle_res = await self.session.execute(bundle_stmt)
        key_ids = [row[0] for row in bundle_res.all() if row[0] is not None]
        return list(dict.fromkeys(key_ids))

    async def touch(
            self,
            *,
            device_id: UUID,
            last_seen_at,
            user_agent: str | None,
            device_model: str | None = None,
            platform: str | None = None,
            os_version: str | None = None,
    ) -> None:
        values = {"last_seen_at": last_seen_at, "user_agent": user_agent}
        if device_model is not None:
            values["device_model"] = device_model
        if platform is not None:
            values["platform"] = platform
        if os_version is not None:
            values["os_version"] = os_version
        await self.session.execute(
            update(self.model)
            .where(self.model.id == device_id)
            .values(**values)
        )


class SubscriptionDeviceKeyRepository(BaseRepository[SubscriptionDeviceKey]):
    def __init__(self, session: AsyncSession):
        super().__init__(SubscriptionDeviceKey, session)

    async def list_by_device(
            self,
            subscription_device_id: UUID,
            *,
            active_only: bool = False,
    ) -> list[SubscriptionDeviceKey]:
        stmt = select(self.model).where(
            self.model.subscription_device_id == subscription_device_id,
        )
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        stmt = stmt.order_by(self.model.is_primary.desc(), self.model.created_at.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_by_device_ids(
            self,
            subscription_device_ids: list[UUID],
            *,
            active_only: bool = False,
    ) -> list[SubscriptionDeviceKey]:
        normalized = list(dict.fromkeys(subscription_device_ids))
        if not normalized:
            return []

        stmt = select(self.model).where(
            self.model.subscription_device_id.in_(normalized),
        )
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        stmt = stmt.order_by(
            self.model.subscription_device_id.asc(),
            self.model.is_primary.desc(),
            self.model.created_at.asc(),
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

