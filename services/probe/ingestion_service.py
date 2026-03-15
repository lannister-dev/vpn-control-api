from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.alerts.service import AlertService, get_alert_service
from services.config import get_settings
from services.nodes.repository import VpnNodeRepository
from services.routes.repository import RouteRepository
from services.routes.schemas import RouteStateUpdate
from services.routes.state_machine import resolve_probe_block, resolve_probe_recover
from services.probe.repository import ProbeSignalRepository
from services.nodes.schemas import NodeRole
from services.probe.schemas import (
    ProbeReportIn,
    ProbeReportOut,
    ProbeSignalInternalCreate,
    ProbeTargetOut,
)
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import PROBE_REPORT_TOTAL
from shared.utils.logger import StructuredLogger


logger_probe = StructuredLogger(logging.getLogger("probe-ingestion-service"))


class ProbeIngestionService:
    def __init__(
            self,
            *,
            node_repository: VpnNodeRepository,
            probe_repository: ProbeSignalRepository,
            route_repository: RouteRepository,
            alert_service: AlertService,
            target_port: int,
            retention_days: int,
            auto_route_health_enabled: bool,
            route_block_cooldown_hours: int,
    ):
        self.node_repository = node_repository
        self.probe_repository = probe_repository
        self.route_repository = route_repository
        self.alert_service = alert_service
        self.target_port = target_port
        self.retention_days = retention_days
        self.auto_route_health_enabled = auto_route_health_enabled
        self.route_block_cooldown_hours = max(1, route_block_cooldown_hours)

    async def report(self, payload: ProbeReportIn) -> ProbeReportOut:
        node = await self.node_repository.get_by_id(payload.node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")

        checked_at = payload.checked_at or datetime.now(timezone.utc)
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)

        create_data = ProbeSignalInternalCreate(
            node_id=payload.node_id,
            source=payload.source,
            is_reachable=payload.is_reachable,
            latency_ms=payload.latency_ms,
            error=payload.error,
            checked_at=checked_at,
            details=payload.details,
        )
        previous = await self.probe_repository.get_latest_for_node(
            node_id=payload.node_id,
            source=payload.source,
        )
        row = await self.probe_repository.create(
            create_data.model_dump()
        )
        latest = await self.probe_repository.get_latest_for_node(
            node_id=payload.node_id,
            source=payload.source,
        )
        status = "reachable" if payload.is_reachable else "failed"
        PROBE_REPORT_TOTAL.labels(status=status).inc()
        if latest is not None and latest.id == row.id:
            await self._maybe_send_probe_alert(
                node=node,
                source=payload.source,
                previous=previous,
                current=row,
            )
            await self._apply_route_health_policy(
                node=node,
                signal=row,
            )
        else:
            logger_probe.info(
                "probe_report_stale_side_effects_skipped",
                node_id=str(payload.node_id),
                source=payload.source,
                report_id=str(row.id),
            )
        return ProbeReportOut.model_validate(row)

    async def list_targets(
            self,
            *,
            role: NodeRole | None = NodeRole.backend,
            include_draining: bool = False,
            include_disabled: bool = False,
    ) -> list[ProbeTargetOut]:
        role_value = role.value if role is not None else None
        rows = await self.node_repository.list_public(role=role_value)

        targets: list[ProbeTargetOut] = []
        for node in rows:
            if not include_disabled and not node.is_enabled:
                continue
            if not include_draining and node.is_draining:
                continue

            host = (node.public_domain or "").strip()
            if not host:
                continue

            node_role = node.role

            targets.append(
                ProbeTargetOut(
                    node_id=node.id,
                    node_name=node.name,
                    role=node_role,
                    region=node.region,
                    host=host,
                    port=self.target_port,
                )
            )

        targets.sort(key=lambda item: (item.region, item.node_name))
        return targets

    async def list_recent(
            self,
            *,
            limit: int,
            node_id: UUID | None,
            source: str | None,
    ) -> list[ProbeReportOut]:
        rows = await self.probe_repository.list_recent(
            limit=limit,
            node_id=node_id,
            source=source,
        )
        return [ProbeReportOut.model_validate(row) for row in rows]

    async def _maybe_send_probe_alert(
            self,
            *,
            node,
            source: str,
            previous,
            current,
    ) -> None:
        should_alert = False
        if previous is None:
            should_alert = not current.is_reachable
        else:
            should_alert = bool(previous.is_reachable) != bool(current.is_reachable)

        if not should_alert:
            return

        await self.alert_service.send_probe_status_change(
            node_id=node.id,
            node_name=node.name,
            region=node.region,
            source=source,
            is_reachable=current.is_reachable,
            checked_at=current.checked_at,
            error=current.error,
        )

    async def cleanup_old_signals(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        deleted_raw = await self.probe_repository.delete_older_than(cutoff=cutoff)
        deleted = deleted_raw if isinstance(deleted_raw, int) else 0
        if deleted > 0:
            logger_probe.info(
                "probe_signal_cleanup",
                deleted=deleted,
                retention_days=self.retention_days,
            )
        return deleted

    async def _apply_route_health_policy(self, *, node, signal) -> None:
        if not self.auto_route_health_enabled:
            return
        if node.role != NodeRole.backend.value:
            return

        routes = await self.route_repository.list_active(node_id=node.id, limit=2000)
        if not routes:
            return

        checked_at = self._to_utc(signal.checked_at)
        if signal.is_reachable:
            await self._recover_routes_after_probe(routes=routes, checked_at=checked_at)
            return
        await self._block_routes_after_probe(routes=routes, checked_at=checked_at)

    async def _block_routes_after_probe(self, *, routes: list, checked_at: datetime) -> None:
        for route in routes:
            next_state = resolve_probe_block(
                route=route,
                checked_at=checked_at,
                cooldown_hours=self.route_block_cooldown_hours,
            )
            updated_state = RouteStateUpdate(
                health_status=next_state["health_status"],
                effective_weight=next_state["effective_weight"],
                cooldown_until=next_state["cooldown_until"],
                warmup_stage=next_state["warmup_stage"],
                warmup_started_at=next_state["warmup_started_at"],
                updated_at=datetime.now(timezone.utc),
            )
            await self.route_repository.update_by_id(
                item_id=route.id,
                data=updated_state.model_dump(),
            )

    async def _recover_routes_after_probe(self, *, routes: list, checked_at: datetime) -> None:
        for route in routes:
            next_state = resolve_probe_recover(route=route, checked_at=checked_at)
            if next_state is None:
                continue
            updated_state = RouteStateUpdate(
                health_status=next_state["health_status"],
                effective_weight=next_state["effective_weight"],
                cooldown_until=next_state["cooldown_until"],
                warmup_stage=next_state["warmup_stage"],
                warmup_started_at=next_state["warmup_started_at"],
                updated_at=datetime.now(timezone.utc),
            )
            await self.route_repository.update_by_id(
                item_id=route.id,
                data=updated_state.model_dump(),
            )

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def get_probe_ingestion_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
        alert_service: AlertService = Depends(get_alert_service),
) -> ProbeIngestionService:
    probe_settings = get_settings().probe
    return ProbeIngestionService(
        node_repository=VpnNodeRepository(session),
        probe_repository=ProbeSignalRepository(session),
        route_repository=RouteRepository(session),
        alert_service=alert_service,
        target_port=probe_settings.target_port,
        retention_days=probe_settings.retention_days,
        auto_route_health_enabled=probe_settings.auto_route_health_enabled,
        route_block_cooldown_hours=probe_settings.route_block_cooldown_hours,
    )
