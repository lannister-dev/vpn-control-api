from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.alerts.service import AlertService, get_alert_service
from services.config import get_settings
from services.nodes.repository import VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.placements.transport import NodeAgentPlacementTransport
from services.routes.repository import RouteRepository
from services.routes.schemas import RouteHealthStatus, RouteStateResolution, RouteStateUpdate
from services.routes.state_machine import resolve_probe_block, resolve_probe_recover
from services.probe.repository import ProbeSignalRepository
from services.probe.schemas import (
    ProbeTargetRole,
    ProbeReportIn,
    ProbeReportOut,
    ProbeSignalInternalCreate,
    ProbeSyntheticClientIds,
    ProbeTargetOut,
)
from services.vpn.keys.repository import VpnKeyRepository
from shared.profiles.constants import WS_TLS_DEFAULT_PATH
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import PROBE_REPORT_TOTAL
from shared.utils.logger import StructuredLogger


logger_probe = StructuredLogger(logging.getLogger("probe-ingestion-service"))


class ProbeIngestionService:
    _SYNTHETIC_REPAIR_REASON = "probe_synthetic_self_heal"
    _SYNTHETIC_REPAIR_COOLDOWN_SEC = 300

    def __init__(
            self,
            *,
            node_repository: VpnNodeRepository,
            probe_repository: ProbeSignalRepository,
            route_repository: RouteRepository,
            placement_repository: UserPlacementRepository,
            placement_transport: NodeAgentPlacementTransport,
            key_repository: VpnKeyRepository,
            alert_service: AlertService,
            target_port: int,
            edge_public_domain: str,
            synthetic_probe_client_ids: ProbeSyntheticClientIds,
            retention_days: int,
            auto_route_health_enabled: bool,
            route_block_cooldown_hours: int,
            route_suspected_after_failures: int = 2,
            route_degraded_after_failures: int = 3,
            route_block_after_failures: int = 4,
    ):
        self.node_repository = node_repository
        self.probe_repository = probe_repository
        self.route_repository = route_repository
        self.placement_repository = placement_repository
        self.placement_transport = placement_transport
        self.key_repository = key_repository
        self.alert_service = alert_service
        self.target_port = target_port
        self.edge_public_domain = edge_public_domain
        self.synthetic_probe_client_ids = synthetic_probe_client_ids
        self.retention_days = retention_days
        self.auto_route_health_enabled = auto_route_health_enabled
        self.route_block_cooldown_hours = max(1, route_block_cooldown_hours)
        self.route_suspected_after_failures = max(1, route_suspected_after_failures)
        self.route_degraded_after_failures = max(2, route_degraded_after_failures)
        self.route_block_after_failures = max(3, route_block_after_failures)

    async def report(self, payload: ProbeReportIn) -> ProbeReportOut:
        node = await self.node_repository.get_by_id(payload.node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")

        checked_at = payload.checked_at or datetime.now(timezone.utc)
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)

        route = None
        transport_profile = None
        target = None
        if payload.route_id is not None:
            detailed = await self.route_repository.get_active_detailed_by_id(payload.route_id)
            if detailed is None:
                raise HTTPException(status_code=404, detail="Route not found")
            route, route_node, transport_profile, _agent_state = detailed
            if route.node_id != payload.node_id or route_node.id != payload.node_id:
                raise HTTPException(status_code=409, detail="Route does not belong to node")
            target = self._build_probe_target(
                route=route,
                node=route_node,
                transport_profile=transport_profile,
                include_disabled=True,
                include_draining=True,
            )
            if target is None:
                raise HTTPException(status_code=409, detail="Route is not probeable")

        create_data = ProbeSignalInternalCreate(
            node_id=payload.node_id,
            route_id=payload.route_id,
            transport_profile_id=payload.transport_profile_id or (
                transport_profile.id if transport_profile is not None else None
            ),
            transport_kind=payload.transport_kind or (target.transport_kind if target is not None else None),
            probe_kind=payload.probe_kind,
            target_host=payload.target_host or (target.target_host if target is not None else None),
            target_port=payload.target_port or (target.target_port if target is not None else None),
            error_phase=payload.error_phase,
            source=payload.source,
            is_reachable=payload.is_reachable,
            latency_ms=payload.latency_ms,
            error=payload.error,
            checked_at=checked_at,
            details=payload.details,
        )
        previous = await self._get_previous_signal(payload=payload)
        row = await self.probe_repository.create(
            create_data.model_dump()
        )
        latest = await self._get_previous_signal(payload=payload)
        status = "reachable" if payload.is_reachable else "failed"
        PROBE_REPORT_TOTAL.labels(status=status).inc()
        if latest is not None and latest.id == row.id:
            await self._maybe_send_probe_alert(
                node=node,
                source=payload.source,
                previous=previous,
                current=row,
            )
            await self._maybe_trigger_synthetic_self_heal(
                node=node,
                signal=row,
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
            include_draining: bool = False,
            include_disabled: bool = False,
            role: ProbeTargetRole | None = None,
    ) -> list[ProbeTargetOut]:
        rows = await self.route_repository.list_active_detailed(limit=5000)
        probe_client_ids_by_target = await self._resolve_probe_client_ids_by_target(rows=rows)

        targets: list[ProbeTargetOut] = []
        for route, node, transport_profile, _agent_state in rows:
            if node.role == "whitelist_entry":
                continue
            if role is not None and not self._matches_target_role(node=node, role=role):
                continue
            target = self._build_probe_target(
                route=route,
                node=node,
                transport_profile=transport_profile,
                include_disabled=include_disabled,
                include_draining=include_draining,
                probe_client_id=probe_client_ids_by_target.get(
                    (node.id, self._transport_kind_for_profile(transport_profile)),
                ),
            )
            if target is None:
                continue
            targets.append(target)

        targets.extend(
            await self._list_node_probe_targets(
                include_draining=include_draining,
                include_disabled=include_disabled,
                role=role,
            )
        )
        targets.sort(key=lambda item: (item.region, item.node_name, item.route_name or ""))
        return targets

    async def list_recent(
            self,
            *,
            limit: int,
            node_id: UUID | None,
            route_id: UUID | None,
            source: str | None,
    ) -> list[ProbeReportOut]:
        rows = await self.probe_repository.list_recent(
            limit=limit,
            node_id=node_id,
            route_id=route_id,
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
            route_id=current.route_id,
            transport_kind=current.transport_kind,
            probe_kind=current.probe_kind,
            target_host=current.target_host,
            target_port=current.target_port,
            error_phase=current.error_phase,
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
        route_id = signal.route_id
        if route_id is None:
            logger_probe.info(
                "probe_signal_node_scope_health_policy_skipped",
                node_id=str(node.id),
                signal_id=str(signal.id),
                source=signal.source,
            )
            return
        route = await self.route_repository.get_by_id(route_id)
        if route is None or not route.is_active:
            return

        checked_at = self._to_utc(signal.checked_at)
        if signal.is_reachable:
            await self._recover_route_after_probe(route=route, checked_at=checked_at)
            return
        await self._degrade_route_after_probe(route=route, checked_at=checked_at)

    async def _maybe_trigger_synthetic_self_heal(self, *, node, signal) -> None:
        if signal.is_reachable or signal.route_id is None or signal.probe_kind != "synthetic_vpn":
            return

        transport_kind = signal.transport_kind
        configured_by_transport = self.synthetic_probe_client_ids.configured_transports()
        if transport_kind not in configured_by_transport:
            return

        consecutive = await self.probe_repository.count_consecutive_route_failures(
            route_id=signal.route_id,
            limit=self.route_block_after_failures + 2,
        )
        if consecutive < self.route_suspected_after_failures:
            return

        client_id = configured_by_transport[transport_kind]
        keys = await self.key_repository.list_by_client_ids(
            client_ids=[client_id],
            active_only=True,
        )
        key = next((item for item in keys if item.client_id == client_id), None)
        if key is None:
            return

        placements = await self.placement_repository.list_by_key_id(
            key_id=key.id,
            active_only=True,
            desired_state="active",
        )
        placement = next((item for item in placements if item.backend_node_id == node.id), None)
        if placement is None:
            return

        updated_at = self._to_utc_or_none(getattr(placement, "updated_at", None))
        if (
            getattr(placement, "last_migration_reason", None) == self._SYNTHETIC_REPAIR_REASON
            and updated_at is not None
            and (datetime.now(timezone.utc) - updated_at).total_seconds() < self._SYNTHETIC_REPAIR_COOLDOWN_SEC
        ):
            return

        refreshed = await self.placement_repository.upsert_set_pending(
            key_id=key.id,
            backend_node_id=node.id,
            desired_state="active",
            sticky_until=getattr(placement, "sticky_until", None),
            last_migration_reason=self._SYNTHETIC_REPAIR_REASON,
        )
        await self.placement_transport.enqueue_for_placement_ids([refreshed.id])
        logger_probe.warning(
            "probe_synthetic_self_heal_requeued",
            node_id=str(node.id),
            route_id=str(signal.route_id),
            transport_kind=transport_kind,
            placement_id=str(refreshed.id),
            failures=consecutive,
        )

    async def _degrade_route_after_probe(self, *, route, checked_at: datetime) -> None:
        status = str(route.health_status)
        if status in {RouteHealthStatus.blocked.value, RouteHealthStatus.warming_up.value}:
            return

        consecutive = await self.probe_repository.count_consecutive_route_failures(
            route_id=route.id,
            limit=self.route_block_after_failures + 2,
        )
        logger_probe.info(
            "probe_route_health_consecutive_failures",
            route_id=str(route.id),
            consecutive=consecutive,
            thresholds=f"{self.route_suspected_after_failures}/{self.route_degraded_after_failures}/{self.route_block_after_failures}",
        )

        if consecutive >= self.route_block_after_failures:
            next_state = resolve_probe_block(
                route=route,
                checked_at=checked_at,
                cooldown_hours=0,
            )
        elif consecutive >= self.route_degraded_after_failures:
            if status == RouteHealthStatus.degraded.value:
                return
            next_state = RouteStateResolution(
                health_status=RouteHealthStatus.degraded,
                effective_weight=max(1, int(route.base_weight) // 2),
                cooldown_until=None,
                warmup_stage=None,
                warmup_started_at=None,
            )
        elif consecutive >= self.route_suspected_after_failures:
            if status == RouteHealthStatus.suspected.value:
                return
            next_state = RouteStateResolution(
                health_status=RouteHealthStatus.suspected,
                effective_weight=max(1, int(route.base_weight) // 3),
                cooldown_until=None,
                warmup_stage=None,
                warmup_started_at=None,
            )
        else:
            return

        await self.route_repository.update_by_id(
            item_id=route.id,
            data=RouteStateUpdate(
                health_status=next_state.health_status,
                effective_weight=next_state.effective_weight,
                cooldown_until=next_state.cooldown_until,
                warmup_stage=next_state.warmup_stage,
                warmup_started_at=next_state.warmup_started_at,
                updated_at=datetime.now(timezone.utc),
            ).model_dump(),
        )

    async def _recover_route_after_probe(self, *, route, checked_at: datetime) -> None:
        status = str(route.health_status)
        if status in {RouteHealthStatus.suspected.value, RouteHealthStatus.degraded.value}:
            await self.route_repository.update_by_id(
                item_id=route.id,
                data=RouteStateUpdate(
                    health_status=RouteHealthStatus.healthy,
                    effective_weight=int(route.base_weight),
                    cooldown_until=None,
                    warmup_stage=None,
                    warmup_started_at=None,
                    updated_at=datetime.now(timezone.utc),
                ).model_dump(),
            )
            return
        if status == RouteHealthStatus.blocked.value:
            next_state = resolve_probe_recover(route=route, checked_at=checked_at)
            if next_state is None:
                return
            await self.route_repository.update_by_id(
                item_id=route.id,
                data=RouteStateUpdate(
                    health_status=next_state.health_status,
                    effective_weight=next_state.effective_weight,
                    cooldown_until=next_state.cooldown_until,
                    warmup_stage=next_state.warmup_stage,
                    warmup_started_at=next_state.warmup_started_at,
                    updated_at=datetime.now(timezone.utc),
                ).model_dump(),
            )

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def _get_previous_signal(self, *, payload: ProbeReportIn):
        if payload.route_id is not None:
            return await self.probe_repository.get_latest_for_route(
                route_id=payload.route_id,
                source=payload.source,
            )
        return await self.probe_repository.get_latest_for_node(
            node_id=payload.node_id,
            source=payload.source,
        )

    def _build_probe_target(
            self,
            *,
            route,
            node,
            transport_profile,
            include_disabled: bool,
            include_draining: bool,
            probe_client_id: str | None = None,
    ) -> ProbeTargetOut | None:
        if not include_disabled and not node.is_enabled:
            return None
        if not include_draining and node.is_draining:
            return None

        network = transport_profile.network
        security = transport_profile.security

        if security == "reality" and network == "tcp":
            host = node.reality_ip
            sni = transport_profile.reality_server_name
            public_key = transport_profile.reality_public_key
            short_id = transport_profile.reality_short_id
            if not host or not sni or not public_key or not short_id:
                return None
            return ProbeTargetOut(
                node_id=node.id,
                route_id=route.id,
                route_name=route.name,
                transport_profile_id=transport_profile.id,
                transport_profile_name=transport_profile.name,
                transport_kind="reality",
                probe_kind="synthetic_vpn",
                node_name=node.name,
                region=node.region,
                probe_client_id=probe_client_id,
                target_host=host,
                target_port=transport_profile.port,
                tls_sni=sni,
                tls_fingerprint=transport_profile.tls_fingerprint or "chrome",
                reality_public_key=public_key,
                reality_short_id=short_id,
                reality_server_name=sni,
                flow=transport_profile.flow,
            )

        if security == "tls" and network == "ws":
            if self.edge_public_domain:
                return None
            host = node.public_domain
            if not host:
                return None
            return ProbeTargetOut(
                node_id=node.id,
                route_id=route.id,
                route_name=route.name,
                transport_profile_id=transport_profile.id,
                transport_profile_name=transport_profile.name,
                transport_kind="ws",
                probe_kind="synthetic_vpn",
                node_name=node.name,
                region=node.region,
                probe_client_id=probe_client_id,
                target_host=host,
                target_port=transport_profile.port or self.target_port,
                tls_sni=host,
                tls_fingerprint=transport_profile.tls_fingerprint or "chrome",
                ws_host=host,
                ws_path=WS_TLS_DEFAULT_PATH,
            )

        return None

    async def _list_node_probe_targets(
            self,
            *,
            include_draining: bool,
            include_disabled: bool,
            role: ProbeTargetRole | None,
    ) -> list[ProbeTargetOut]:
        if role not in {None, "all", "whitelist_entry"}:
            return []

        nodes = await self.node_repository.list_public()
        targets: list[ProbeTargetOut] = []
        for node in nodes:
            if node.role != "whitelist_entry":
                continue
            if role is not None and not self._matches_target_role(node=node, role=role):
                continue
            target = self._build_node_probe_target(
                node=node,
                include_disabled=include_disabled,
                include_draining=include_draining,
            )
            if target is None:
                continue
            targets.append(target)
        return targets

    def _build_node_probe_target(
            self,
            *,
            node,
            include_disabled: bool,
            include_draining: bool,
    ) -> ProbeTargetOut | None:
        if not include_disabled and not node.is_enabled:
            return None
        if not include_draining and node.is_draining:
            return None

        host = node.public_domain or node.reality_ip
        if not host:
            return None

        return ProbeTargetOut(
            node_id=node.id,
            transport_kind="reality",
            probe_kind="tcp_connect",
            node_name=node.name,
            region=node.region,
            target_host=host,
            target_port=self.target_port,
        )

    async def _resolve_probe_client_ids_by_target(self, *, rows: list[tuple]) -> dict[tuple[UUID, str], str]:
        configured_by_transport = self.synthetic_probe_client_ids.configured_transports()
        if not configured_by_transport:
            return {}

        backend_ids_by_transport: dict[str, set[UUID]] = {}
        for route, node, transport_profile, _agent_state in rows:
            transport_kind = self._transport_kind_for_profile(transport_profile)
            if transport_kind is None or transport_kind not in configured_by_transport:
                continue
            backend_ids_by_transport.setdefault(transport_kind, set()).add(node.id)

        if not backend_ids_by_transport:
            return {}

        keys = await self.key_repository.list_by_client_ids(
            client_ids=list(configured_by_transport.values()),
            active_only=True,
        )
        key_by_client_id = {key.client_id: key for key in keys if key.client_id}

        resolved: dict[tuple[UUID, str], str] = {}
        for transport_kind, client_id in configured_by_transport.items():
            key = key_by_client_id.get(client_id)
            if key is None:
                continue
            if key.transport != transport_kind:
                continue
            expected_backend_ids = backend_ids_by_transport.get(transport_kind, set())
            if not expected_backend_ids:
                continue
            placements = await self.placement_repository.list_by_key_id(
                key_id=key.id,
                active_only=True,
                desired_state="active",
            )
            for placement in placements:
                if placement.backend_node_id not in expected_backend_ids:
                    continue
                resolved[(placement.backend_node_id, transport_kind)] = client_id
        return resolved

    @staticmethod
    def _to_utc_or_none(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _transport_kind_for_profile(transport_profile) -> str | None:
        network = transport_profile.network
        security = transport_profile.security
        if security == "reality" and network == "tcp":
            return "reality"
        if security == "tls" and network == "ws":
            return "ws"
        return None

    @staticmethod
    def _matches_target_role(*, node, role: ProbeTargetRole) -> bool:
        if role == "all":
            return True
        return node.role == role


def get_probe_ingestion_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
        alert_service: AlertService = Depends(get_alert_service),
) -> ProbeIngestionService:
    probe_settings = get_settings().probe
    return ProbeIngestionService(
        node_repository=VpnNodeRepository(session),
        probe_repository=ProbeSignalRepository(session),
        route_repository=RouteRepository(session),
        placement_repository=UserPlacementRepository(session),
        placement_transport=NodeAgentPlacementTransport(session),
        key_repository=VpnKeyRepository(session),
        alert_service=alert_service,
        target_port=probe_settings.target_port,
        edge_public_domain=get_settings().edge.public_domain,
        synthetic_probe_client_ids=ProbeSyntheticClientIds(
            reality=probe_settings.synthetic_reality_client_id,
            ws=probe_settings.synthetic_ws_client_id,
        ),
        retention_days=probe_settings.retention_days,
        auto_route_health_enabled=probe_settings.auto_route_health_enabled,
        route_block_cooldown_hours=probe_settings.route_block_cooldown_hours,
        route_suspected_after_failures=probe_settings.route_suspected_after_failures,
        route_degraded_after_failures=probe_settings.route_degraded_after_failures,
        route_block_after_failures=probe_settings.route_block_after_failures,
    )
