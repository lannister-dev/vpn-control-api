from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.alerts.service import AlertService, get_alert_service
from services.config import get_settings
from services.nodes.repository import VpnNodeRepository

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
            alert_service: AlertService,
            target_port: int,
            retention_days: int,
    ):
        self.node_repository = node_repository
        self.probe_repository = probe_repository
        self.alert_service = alert_service
        self.target_port = target_port
        self.retention_days = retention_days

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
        status = "reachable" if payload.is_reachable else "failed"
        PROBE_REPORT_TOTAL.labels(status=status).inc()
        await self._maybe_send_probe_alert(
            node=node,
            source=payload.source,
            previous=previous,
            current=row,
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
            if not include_disabled and not getattr(node, "is_enabled", True):
                continue
            if not include_draining and getattr(node, "is_draining", False):
                continue

            host = (getattr(node, "public_domain", "") or "").strip()
            if not host:
                continue

            node_role = getattr(node, "role", NodeRole.backend.value)
            if not isinstance(node_role, str):
                node_role = str(node_role)

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


def get_probe_ingestion_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
        alert_service: AlertService = Depends(get_alert_service),
) -> ProbeIngestionService:
    probe_settings = get_settings().probe
    return ProbeIngestionService(
        node_repository=VpnNodeRepository(session),
        probe_repository=ProbeSignalRepository(session),
        alert_service=alert_service,
        target_port=probe_settings.target_port,
        retention_days=probe_settings.retention_days,
    )
