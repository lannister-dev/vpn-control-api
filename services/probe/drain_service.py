from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode
from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.nodes.schemas import NodeHeartbeatMeta, VpnNodeUpdate
from services.placements.service import UserPlacementService, get_user_placement_service
from services.placements.schemas import PlacementMigrateBackendIn
from services.probe.repository import ProbeSignalRepository
from services.probe.schemas import (
    ProbeAutoDrainMigrateIn,
    ProbeAutoDrainMigrateItemOut,
    ProbeAutoDrainMigrateOut,
    ProbeDrainMigrateIn,
    ProbeDrainMigrateOut,
)
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import PROBE_ACTION_TOTAL
from shared.utils.logger import StructuredLogger


logger_probe = StructuredLogger(logging.getLogger("probe-drain-service"))


class ProbeDrainService:
    _PROBE_DRAIN_REASON_PREFIX = "probe_"

    def __init__(
            self,
            *,
            node_repository: VpnNodeRepository,
            probe_repository: ProbeSignalRepository,
            placement_service: UserPlacementService,
            node_state_repository: NodeAgentStateRepository | None = None,
    ):
        self.node_repository = node_repository
        self.probe_repository = probe_repository
        self.placement_service = placement_service
        self.node_state_repository = node_state_repository

    async def drain_and_migrate_backend(
            self,
            payload: ProbeDrainMigrateIn,
    ) -> ProbeDrainMigrateOut:
        action = "drain_migrate_backend"
        try:
            source_node = await self.node_repository.get_by_id(payload.source_backend_id)
            if not source_node:
                raise HTTPException(status_code=404, detail="Source node not found")

            latest = await self._validate_probe_failure_for_node(
                node_id=payload.source_backend_id,
                source=payload.source,
                require_recent_failure=payload.require_recent_failure,
                max_probe_age_sec=payload.max_probe_age_sec,
                min_consecutive_failures=payload.min_consecutive_failures,
            )

            source_was_draining = source_node.is_draining
            if not source_was_draining:
                drained_at = datetime.now(timezone.utc)
                await self.node_repository.update_by_id(
                    payload.source_backend_id,
                    VpnNodeUpdate(
                        is_draining=True,
                    ).model_dump(exclude_unset=True),
                )
                await self._set_probe_drain_reason(
                    node_id=payload.source_backend_id,
                    drain_reason=self._normalize_probe_drain_reason(payload.last_migration_reason),
                    drained_at=drained_at,
                )

            try:
                migration = await self.placement_service.migrate_backend(
                    PlacementMigrateBackendIn(
                        source_backend_id=payload.source_backend_id,
                        target_backend_id=payload.target_backend_id,
                        last_migration_reason=payload.last_migration_reason,
                    )
                )
            except HTTPException:
                if not source_was_draining:
                    await self.node_repository.update_by_id(
                        payload.source_backend_id,
                        VpnNodeUpdate(
                            is_draining=False,
                        ).model_dump(exclude_unset=True),
                    )
                    await self._clear_probe_drain_reason(node_id=payload.source_backend_id)
                raise
            PROBE_ACTION_TOTAL.labels(action=action, result="success").inc()
            return ProbeDrainMigrateOut(
                source_backend_id=migration.source_backend_id,
                target_backend_id=migration.target_backend_id,
                migrated_count=migration.migrated_count,
                drained=True,
                probe_report_id=latest.id if latest else None,
            )
        except HTTPException as exc:
            logger_probe.warning(
                "drain_and_migrate_backend_rejected",
                source_backend_id=str(payload.source_backend_id),
                detail=str(exc.detail),
            )
            PROBE_ACTION_TOTAL.labels(action=action, result="rejected").inc()
            raise

    async def auto_drain_and_migrate_backends(
            self,
            payload: ProbeAutoDrainMigrateIn,
    ) -> ProbeAutoDrainMigrateOut:
        items: list[ProbeAutoDrainMigrateItemOut] = []
        processed = 0
        migrated = 0

        nodes = await self._resolve_auto_nodes(payload)
        for node in nodes:
            if processed >= payload.max_nodes:
                break
            processed += 1

            node_id = node.id

            if not node.is_active or not node.is_enabled:
                logger_probe.info(
                    "auto_drain_skipped_inactive",
                    node_id=str(node_id),
                    is_active=node.is_active,
                    is_enabled=node.is_enabled,
                )
                items.append(
                    ProbeAutoDrainMigrateItemOut(
                        source_backend_id=node_id,
                        action="skipped",
                        detail="Node is not active/enabled",
                    )
                )
                continue
            if node.is_draining and not payload.include_already_draining:
                logger_probe.info(
                    "auto_drain_skipped_already_draining",
                    node_id=str(node_id),
                )
                items.append(
                    ProbeAutoDrainMigrateItemOut(
                        source_backend_id=node_id,
                        action="skipped",
                        detail="Node already draining",
                    )
                )
                continue

            try:
                latest = await self._validate_probe_failure_for_node(
                    node_id=node_id,
                    source=payload.source,
                    require_recent_failure=payload.require_recent_failure,
                    max_probe_age_sec=payload.max_probe_age_sec,
                    min_consecutive_failures=payload.min_consecutive_failures,
                )
            except HTTPException as exc:
                logger_probe.info(
                    "auto_drain_skipped_probe_policy",
                    node_id=str(node_id),
                    detail=str(exc.detail),
                )
                items.append(
                    ProbeAutoDrainMigrateItemOut(
                        source_backend_id=node_id,
                        action="skipped",
                        detail=str(exc.detail),
                    )
                )
                continue

            if payload.dry_run:
                logger_probe.info(
                    "auto_drain_would_migrate",
                    node_id=str(node_id),
                    probe_report_id=str(latest.id) if latest else None,
                )
                items.append(
                    ProbeAutoDrainMigrateItemOut(
                        source_backend_id=node_id,
                        action="would_migrate",
                        detail="Eligible by probe policy",
                        probe_report_id=latest.id if latest else None,
                    )
                )
                continue

            try:
                result = await self.drain_and_migrate_backend(
                    ProbeDrainMigrateIn(
                        source_backend_id=node_id,
                        target_backend_id=payload.target_backend_id,
                        require_recent_failure=False,
                        max_probe_age_sec=payload.max_probe_age_sec,
                        min_consecutive_failures=payload.min_consecutive_failures,
                        source=payload.source,
                        last_migration_reason=payload.last_migration_reason,
                    )
                )
                migrated += 1
                items.append(
                    ProbeAutoDrainMigrateItemOut(
                        source_backend_id=result.source_backend_id,
                        action="migrated",
                        target_backend_id=result.target_backend_id,
                        migrated_count=result.migrated_count,
                        probe_report_id=result.probe_report_id,
                    )
                )
            except HTTPException as exc:
                logger_probe.warning(
                    "auto_drain_migration_skipped",
                    node_id=str(node_id),
                    detail=str(exc.detail),
                )
                items.append(
                    ProbeAutoDrainMigrateItemOut(
                        source_backend_id=node_id,
                        action="skipped",
                        detail=str(exc.detail),
                    )
                )

        return ProbeAutoDrainMigrateOut(
            processed=processed,
            migrated=migrated,
            skipped=processed - migrated,
            dry_run=payload.dry_run,
            items=items,
        )

    async def _resolve_auto_nodes(self, payload: ProbeAutoDrainMigrateIn) -> list[VpnNode]:
        if payload.backend_node_ids is None:
            return list(await self.node_repository.list())
        rows = await self.node_repository.list_by_ids(payload.backend_node_ids)
        by_id = {row.id: row for row in rows}
        return [by_id[node_id] for node_id in payload.backend_node_ids if node_id in by_id]

    async def _validate_probe_failure_for_node(
            self,
            *,
            node_id: UUID,
            source: str | None,
            require_recent_failure: bool,
            max_probe_age_sec: int,
            min_consecutive_failures: int,
    ):
        latest = await self.probe_repository.get_latest_for_backend_node(
            node_id=node_id,
            source=source,
        )
        if not require_recent_failure:
            return latest

        if latest is None:
            raise HTTPException(status_code=409, detail="No probe report for source backend")
        if latest.is_reachable:
            raise HTTPException(status_code=409, detail="Latest probe is healthy")

        checked_at = latest.checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        max_age = timedelta(seconds=max_probe_age_sec)
        if datetime.now(timezone.utc) - checked_at > max_age:
            raise HTTPException(status_code=409, detail="Latest probe failure is stale")

        if min_consecutive_failures > 1:
            recent = await self.probe_repository.list_recent_for_backend_node(
                limit=max(20, min_consecutive_failures * 3),
                node_id=node_id,
                source=source,
            )
            consecutive_failures = 0
            for signal in recent:
                if signal.is_reachable:
                    break
                consecutive_failures += 1
            if consecutive_failures < min_consecutive_failures:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Insufficient consecutive probe failures: "
                        f"{consecutive_failures}/{min_consecutive_failures}"
                    ),
                )
        return latest

    async def _set_probe_drain_reason(
            self,
            *,
            node_id: UUID,
            drain_reason: str,
            drained_at: datetime,
    ) -> None:
        if self.node_state_repository is None:
            return
        state = await self.node_state_repository.get_one_by(node_id=node_id)
        if state is None:
            return
        details = dict(state.details) if isinstance(state.details, dict) else {}
        heartbeat_meta = self._load_heartbeat_meta(details)
        heartbeat_meta.drain_reason = drain_reason
        heartbeat_meta.drained_at = drained_at
        details["heartbeat"] = heartbeat_meta.model_dump(mode="json", exclude_none=True)
        await self.node_state_repository.update_by_node_id(node_id, {"details": details})

    async def _clear_probe_drain_reason(self, *, node_id: UUID) -> None:
        if self.node_state_repository is None:
            return
        state = await self.node_state_repository.get_one_by(node_id=node_id)
        if state is None:
            return
        details = dict(state.details) if isinstance(state.details, dict) else {}
        heartbeat_meta = self._load_heartbeat_meta(details)
        changed = False
        if heartbeat_meta.drain_reason is not None:
            heartbeat_meta.drain_reason = None
            changed = True
        if heartbeat_meta.drained_at is not None:
            heartbeat_meta.drained_at = None
            changed = True
        if not changed:
            return
        details["heartbeat"] = heartbeat_meta.model_dump(mode="json", exclude_none=True)
        await self.node_state_repository.update_by_node_id(node_id, {"details": details})

    def _normalize_probe_drain_reason(self, value: str | None) -> str:
        normalized = (value or "").strip()
        if normalized.startswith(self._PROBE_DRAIN_REASON_PREFIX):
            return normalized
        if normalized:
            return f"{self._PROBE_DRAIN_REASON_PREFIX}{normalized}"
        return "probe_failure"

    @staticmethod
    def _load_heartbeat_meta(details: dict) -> NodeHeartbeatMeta:
        heartbeat_raw = details.get("heartbeat")
        heartbeat_data = heartbeat_raw if isinstance(heartbeat_raw, dict) else {}
        return NodeHeartbeatMeta.model_validate(heartbeat_data)


def get_probe_drain_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
        placement_service: UserPlacementService = Depends(get_user_placement_service),
) -> ProbeDrainService:
    return ProbeDrainService(
        node_repository=VpnNodeRepository(session),
        probe_repository=ProbeSignalRepository(session),
        placement_service=placement_service,
        node_state_repository=NodeAgentStateRepository(session),
    )
