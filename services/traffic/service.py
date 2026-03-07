from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.placements.repository import UserPlacementRepository
from services.traffic.repository import TrafficUsageRepository
from services.placements.schemas import PlacementDesiredState
from services.traffic.schemas import (
    TrafficHistoryItemOut,
    TrafficHistoryListOut,
    TrafficKeySummaryListOut,
    TrafficKeySummaryOut,
    TrafficUsageCreate,
    UserTrafficIn,
)
from services.vpn.keys.repository import VpnKeyRepository
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import VPN_KEY_OPERATION_TOTAL
from services.traffic.constants import _MIGRATION_REASON, _MIB
from shared.utils.logger import StructuredLogger

logger_traffic = StructuredLogger(logging.getLogger("traffic-service"))


class UserTrafficService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.key_repository = VpnKeyRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.traffic_usage_repository = TrafficUsageRepository(session)

    async def ingest_users_traffic(self, raw_payload: bytes) -> dict[str, int]:
        try:
            payload_obj = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger_traffic.warning("users_traffic_payload_invalid", error=str(exc))
            return {"processed": 0, "revoked": 0}

        if not isinstance(payload_obj, list):
            logger_traffic.warning("users_traffic_payload_not_list")
            return {"processed": 0, "revoked": 0}

        parsed: list[UserTrafficIn] = []
        for item in payload_obj:
            if not isinstance(item, dict):
                continue
            try:
                parsed.append(UserTrafficIn.model_validate(item))
            except Exception:
                continue

        if not parsed:
            return {"processed": 0, "revoked": 0}

        keys = await self.key_repository.list_by_client_ids(
            client_ids=[item.identifier for item in parsed],
            active_only=True,
        )
        if not keys:
            return {"processed": 0, "revoked": 0}

        key_by_client = {key.client_id: key for key in keys}
        now = datetime.now(timezone.utc)
        processed = 0
        revoked = 0
        history_rows: list[TrafficUsageCreate] = []

        for traffic in parsed:
            key = key_by_client.get(traffic.identifier)
            if key is None:
                continue

            reported_total = traffic.total_bytes
            if reported_total <= 0:
                reported_total = traffic.uplink_bytes + traffic.downlink_bytes

            delta = self._compute_delta(
                new_total=reported_total,
                old_total=key.last_reported_total_bytes or 0,
            )
            if delta <= 0:
                key.last_reported_total_bytes = reported_total
                continue

            processed += 1
            key.last_reported_total_bytes = reported_total
            key.used_traffic_bytes = int(key.used_traffic_bytes or 0) + delta
            key.updated_at = now
            history_rows.append(
                TrafficUsageCreate(
                    key_id=key.id,
                    delta_bytes=delta,
                    reported_total_bytes=reported_total,
                )
            )

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

    @staticmethod
    def _compute_delta(*, new_total: int, old_total: int) -> int:
        if new_total < 0:
            return 0
        if old_total < 0:
            return new_total
        if new_total >= old_total:
            return new_total - old_total
        # Xray counter may reset after process restart.
        return new_total

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
