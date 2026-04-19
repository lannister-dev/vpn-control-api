from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.nodes.agent.repository import NodeTransportOutboxRepository
from services.nodes.agent.schemas import AgentSubjects, OutboxEnqueueItem, UpstreamChangedPayload
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import NodeUpstreamUpdate
from services.routes.exceptions import RouteCooldownActiveError
from services.routes.policy import DEFAULT_WARMUP_STAGES
from services.routes.repository import RouteRepository, TransportProfileRepository
from services.routes.schemas import (
    RouteCreateData,
    RouteCreateIn,
    RouteFieldsUpdate,
    RouteHealthStatus,
    RouteHealthUpdateIn,
    RouteOut,
    RouteReactivationUpdate,
    RouteStateUpdate,
    RouteUpdateIn,
    RouteWarmupStage,
    RouteWarmupTickResult,
    RouteWarmupTickOut,
    ProfileReactivationUpdate,
    TransportNetwork,
    TransportProfileCreateIn,
    TransportProfileOut,
    TransportProtocol,
    TransportSecurity,
)
from services.routes.state_machine import (
    initial_warmup_weight,
    resolve_route_health_action,
    resolve_warmup_tick,
)
from services.routes.types import ENTRY_NODE_ROLES, RouteNodeRole
from services.routes.utils import build_route_out, normalized_node_role, to_utc_or_none
from shared.database.session import AsyncDatabase


class RouteService:
    WARMUP_STAGES: list[RouteWarmupStage] = list(DEFAULT_WARMUP_STAGES)

    def __init__(self, session: AsyncSession):
        self.settings = get_settings()
        self.node_state_stale_after_sec = max(30, int(self.settings.node_agent.stale_after_sec))
        self.session = session
        self.node_repository = VpnNodeRepository(session)
        self.transport_repository = TransportProfileRepository(session)
        self.route_repository = RouteRepository(session)
        self.outbox_repository = NodeTransportOutboxRepository(session)
        nats_cfg = self.settings.nats
        self._subjects = AgentSubjects(
            command_prefix=nats_cfg.js_command_subject_prefix,
            result_prefix=nats_cfg.js_result_subject_prefix,
            snapshot_prefix=nats_cfg.js_snapshot_subject_prefix,
            heartbeat_prefix=nats_cfg.js_heartbeat_subject_prefix,
            sync_report_prefix=nats_cfg.js_sync_report_subject_prefix,
        )

    async def create_transport_profile(
            self,
            payload: TransportProfileCreateIn,
    ) -> TransportProfileOut:
        existing = await self.transport_repository.get_one_by(name=payload.name)
        if existing and existing.is_active:
            raise HTTPException(status_code=409, detail="Transport profile already exists")
        payload = self._normalize_transport_profile_payload(payload)

        if existing and not existing.is_active:
            update_payload = ProfileReactivationUpdate(
                **payload.model_dump(),
                is_active=True,
            )
            updated = await self.transport_repository.update_by_id(
                existing.id,
                update_payload.model_dump(),
            )
            if not updated:
                raise HTTPException(status_code=500, detail="Failed to create transport profile")
            return TransportProfileOut.model_validate(updated)

        created = await self.transport_repository.create(payload.model_dump())
        return TransportProfileOut.model_validate(created)

    def _normalize_transport_profile_payload(
            self,
            payload: TransportProfileCreateIn,
    ) -> TransportProfileCreateIn:
        if payload.protocol != TransportProtocol.vless:
            raise HTTPException(status_code=422, detail=f"Unsupported protocol: {payload.protocol.value}")

        grpc_service_name = payload.grpc_service_name
        if payload.security == TransportSecurity.reality:
            if payload.network != TransportNetwork.tcp:
                raise HTTPException(status_code=422, detail="reality transport requires network=tcp")
            if not payload.reality_public_key or not payload.reality_short_id or not payload.reality_server_name:
                raise HTTPException(
                    status_code=422,
                    detail="reality transport requires reality_public_key, reality_short_id and reality_server_name",
                )
            if payload.grpc_service_name:
                raise HTTPException(status_code=422, detail="reality transport does not support grpc_service_name")
        elif payload.security == TransportSecurity.tls:
            if payload.network not in {TransportNetwork.grpc, TransportNetwork.ws}:
                raise HTTPException(status_code=422, detail="tls transport supports only network=grpc or network=ws")
            if payload.reality_public_key or payload.reality_short_id or payload.reality_server_name:
                raise HTTPException(
                    status_code=422,
                    detail="tls transport does not support reality_* fields",
                )
            if payload.flow:
                raise HTTPException(status_code=422, detail="tls transport does not support flow")
            if payload.network == TransportNetwork.grpc:
                grpc_service_name = grpc_service_name or "vl"
            elif grpc_service_name:
                raise HTTPException(status_code=422, detail="ws transport does not support grpc_service_name")
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported security: {payload.security.value}")

        return TransportProfileCreateIn(
            name=payload.name,
            protocol=payload.protocol,
            network=payload.network,
            security=payload.security,
            flow=payload.flow,
            reality_public_key=payload.reality_public_key,
            reality_short_id=payload.reality_short_id,
            reality_server_name=payload.reality_server_name,
            tls_fingerprint=payload.tls_fingerprint,
            grpc_service_name=grpc_service_name,
            port=payload.port,
        )

    async def list_transport_profiles(self, *, limit: int = 200) -> list[TransportProfileOut]:
        rows = await self.transport_repository.list_active(limit=limit)
        return [TransportProfileOut.model_validate(row) for row in rows]

    async def create_route(self, payload: RouteCreateIn) -> RouteOut:
        node = await self.node_repository.get_by_id(payload.node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        if normalized_node_role(node) != RouteNodeRole.backend:
            raise HTTPException(status_code=422, detail="Route backend node must have role=backend")

        if payload.entry_node_id is not None:
            entry_node = await self.node_repository.get_by_id(payload.entry_node_id)
            if not entry_node:
                raise HTTPException(status_code=404, detail="Entry node not found")
            entry_role = normalized_node_role(entry_node)
            if entry_role not in ENTRY_NODE_ROLES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Route entry node must have role in {sorted(r.value for r in ENTRY_NODE_ROLES)}",
                )

        tp = await self.transport_repository.get_by_id(payload.transport_profile_id)
        if not tp or not tp.is_active:
            raise HTTPException(status_code=404, detail="Transport profile not found")

        existing = await self.route_repository.get_one_by(name=payload.name)
        if existing and existing.is_active:
            raise HTTPException(status_code=409, detail="Route already exists")

        effective_weight = payload.effective_weight
        if effective_weight is None:
            effective_weight = payload.base_weight
        if effective_weight > payload.base_weight:
            raise HTTPException(status_code=422, detail="effective_weight must be <= base_weight")

        now = datetime.now(timezone.utc)
        cooldown_until: datetime | None = None
        warmup_stage: int | None = None
        warmup_started_at: datetime | None = None
        resolved_effective_weight = effective_weight

        if payload.health_status == RouteHealthStatus.blocked:
            resolved_effective_weight = 0
            cooldown_until = now + timedelta(hours=6)
        elif payload.health_status == RouteHealthStatus.warming_up:
            warmup_stage = 0
            warmup_started_at = now
            resolved_effective_weight = initial_warmup_weight(base_weight=payload.base_weight)

        create_payload = RouteCreateData(
            name=payload.name,
            node_id=payload.node_id,
            entry_node_id=payload.entry_node_id,
            transport_profile_id=payload.transport_profile_id,
            health_status=payload.health_status,
            base_weight=payload.base_weight,
            effective_weight=resolved_effective_weight,
            cooldown_until=cooldown_until,
            warmup_stage=warmup_stage,
            warmup_started_at=warmup_started_at,
            is_active=True,
        )

        if existing and not existing.is_active:
            update_payload = RouteReactivationUpdate(
                **create_payload.model_dump(),
            )
            result = await self.route_repository.update_by_id(
                existing.id,
                update_payload.model_dump(),
            )
            if not result:
                raise HTTPException(status_code=500, detail="Failed to create route")
        else:
            result = await self.route_repository.create(create_payload.model_dump())

        if payload.entry_node_id is not None:
            await self._sync_entry_upstream(
                entry_node_id=payload.entry_node_id,
                backend_node_id=payload.node_id,
                backend_node=node,
            )
        return build_route_out(result)

    async def update_route(self, route_id: UUID, payload: RouteUpdateIn) -> RouteOut:
        route = await self.route_repository.get_by_id(route_id)
        if not route or not route.is_active:
            raise HTTPException(status_code=404, detail="Route not found")

        if not payload.model_fields_set:
            return build_route_out(route)

        update = RouteFieldsUpdate()
        loaded_backend_node = None

        if "name" in payload.model_fields_set:
            existing = await self.route_repository.get_one_by(name=payload.name)
            if existing and existing.is_active and existing.id != route.id:
                raise HTTPException(status_code=409, detail="Route name already exists")
            update.name = payload.name

        if "node_id" in payload.model_fields_set:
            loaded_backend_node = await self.node_repository.get_by_id(payload.node_id)
            if not loaded_backend_node:
                raise HTTPException(status_code=404, detail="Node not found")
            if normalized_node_role(loaded_backend_node) != RouteNodeRole.backend:
                raise HTTPException(
                    status_code=422,
                    detail="Route backend node must have role=backend",
                )
            update.node_id = payload.node_id

        if "entry_node_id" in payload.model_fields_set:
            if payload.entry_node_id is not None:
                entry_node = await self.node_repository.get_by_id(payload.entry_node_id)
                if not entry_node:
                    raise HTTPException(status_code=404, detail="Entry node not found")
                if normalized_node_role(entry_node) not in ENTRY_NODE_ROLES:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Route entry node must have role in {sorted(r.value for r in ENTRY_NODE_ROLES)}",
                    )
            update.entry_node_id = payload.entry_node_id

        if "base_weight" in payload.model_fields_set:
            update.base_weight = payload.base_weight
            if int(route.effective_weight) == int(route.base_weight):
                update.effective_weight = payload.base_weight

        if not update.model_fields_set:
            return build_route_out(route)

        update.updated_at = datetime.now(timezone.utc)
        updated = await self.route_repository.update_by_id(
            route.id, update.model_dump(exclude_unset=True),
        )
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update route")

        resolved_entry = update.entry_node_id if "entry_node_id" in update.model_fields_set else getattr(route, "entry_node_id", None)
        resolved_backend = update.node_id if "node_id" in update.model_fields_set else route.node_id
        if resolved_entry is not None:
            await self._sync_entry_upstream(
                entry_node_id=UUID(str(resolved_entry)),
                backend_node_id=UUID(str(resolved_backend)),
                backend_node=loaded_backend_node,
            )

        return build_route_out(updated)

    async def list_routes(
            self,
            *,
            node_id: UUID | None = None,
            limit: int = 200,
    ) -> list[RouteOut]:
        rows = await self.route_repository.list_active_detailed(node_id=node_id, limit=limit)
        now = datetime.now(timezone.utc)
        return [
            self._build_route_out(
                route=route,
                node=node,
                transport_profile=transport_profile,
                agent_state=agent_state,
                now=now,
            )
            for route, node, transport_profile, agent_state in rows
        ]

    async def update_route_health(
            self,
            route_id: UUID,
            payload: RouteHealthUpdateIn,
    ) -> RouteOut:
        route = await self.route_repository.get_by_id(route_id)
        if not route or not route.is_active:
            raise HTTPException(status_code=404, detail="Route not found")

        now = datetime.now(timezone.utc)
        try:
            next_state = resolve_route_health_action(
                route=route,
                action=payload.action,
                now=now,
                cooldown_hours=payload.cooldown_hours,
                warmup_stages=tuple(self.WARMUP_STAGES),
            )
        except RouteCooldownActiveError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        updated = await self.route_repository.update_by_id(
            item_id=route.id,
            data=RouteStateUpdate(
                health_status=next_state.health_status,
                effective_weight=next_state.effective_weight,
                cooldown_until=next_state.cooldown_until,
                warmup_stage=next_state.warmup_stage,
                warmup_started_at=next_state.warmup_started_at,
                updated_at=now,
            ).model_dump(),
        )
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update route health")
        return build_route_out(updated)

    async def advance_warmup(self) -> RouteWarmupTickOut:
        now = datetime.now(timezone.utc)
        routes = await self.route_repository.list_warming_up()
        processed = 0
        advanced = 0
        finalized = 0

        for route in routes:
            processed += 1
            next_state, tick_result = resolve_warmup_tick(
                route=route,
                now=now,
                warmup_stages=tuple(self.WARMUP_STAGES),
            )
            if next_state is None or tick_result is None:
                continue

            updated = await self.route_repository.update_by_id(
                item_id=route.id,
                data=RouteStateUpdate(
                    health_status=next_state.health_status,
                    effective_weight=next_state.effective_weight,
                    cooldown_until=next_state.cooldown_until,
                    warmup_stage=next_state.warmup_stage,
                    warmup_started_at=next_state.warmup_started_at,
                    updated_at=now,
                ).model_dump(),
            )
            if updated:
                if tick_result == RouteWarmupTickResult.advanced:
                    advanced += 1
                elif tick_result == RouteWarmupTickResult.finalized:
                    finalized += 1

        return RouteWarmupTickOut(
            processed=processed,
            advanced=advanced,
            finalized=finalized,
        )

    async def _sync_entry_upstream(
            self,
            *,
            entry_node_id: UUID,
            backend_node_id: UUID,
            backend_node=None,
    ) -> None:
        entry_node = await self.node_repository.get_by_id(entry_node_id)
        if not entry_node:
            return

        current_upstream = getattr(entry_node, "upstream_node_id", None)
        if current_upstream is not None:
            current_upstream = UUID(str(current_upstream))
        if current_upstream == backend_node_id:
            return

        now = datetime.now(timezone.utc)
        node_update = NodeUpstreamUpdate(
            upstream_node_id=backend_node_id,
            updated_at=now,
        )
        await self.node_repository.update_by_id(
            entry_node_id,
            node_update.model_dump(),
        )

        if backend_node is None:
            backend_node = await self.node_repository.get_by_id(backend_node_id)
        if not backend_node:
            return

        event = UpstreamChangedPayload(
            event_id=str(uuid4()),
            node_id=str(entry_node_id),
            emitted_at=now,
            upstream_node_id=str(backend_node_id),
            upstream_public_domain=str(backend_node.public_domain),
            upstream_reality_ip=getattr(backend_node, "reality_ip", None),
        )
        outbox_item = OutboxEnqueueItem(
            node_id=entry_node_id,
            event_type="upstream_changed",
            aggregate_id=backend_node_id,
            subject=self._subjects.upstream_changed(str(entry_node_id)),
            payload=event.model_dump(mode="json"),
            message_id=f"upstream-changed:{entry_node_id}:{backend_node_id}:{now.isoformat()}",
        )
        await self.outbox_repository.enqueue_many([outbox_item])

    def _build_route_out(
            self,
            *,
            route,
            node,
            transport_profile,
            agent_state,
            now: datetime,
    ) -> RouteOut:
        routing_reason = self._route_routing_reason(
            route=route,
            node=node,
            transport_profile=transport_profile,
            agent_state=agent_state,
            now=now,
        )
        return build_route_out(
            route,
            routing_eligible=routing_reason is None,
            routing_reason=routing_reason,
        )

    def _route_routing_reason(
            self,
            *,
            route,
            node,
            transport_profile,
            agent_state,
            now: datetime,
    ) -> str | None:
        if not bool(route.is_active):
            return "route_inactive"
        if int(route.effective_weight) <= 0:
            return "route_zero_weight"
        if str(route.health_status) not in {
            RouteHealthStatus.healthy.value,
            RouteHealthStatus.warming_up.value,
            RouteHealthStatus.degraded.value,
            RouteHealthStatus.suspected.value,
        }:
            return "route_health_excluded"
        if not bool(transport_profile.is_active):
            return "transport_inactive"
        if not bool(node.is_active):
            return "node_inactive"
        if not bool(node.is_enabled):
            return "node_disabled"
        if bool(node.is_draining):
            return "node_draining"
        if agent_state is None:
            return "agent_state_missing"
        if not bool(agent_state.is_healthy):
            return "agent_unhealthy"
        last_seen_at = to_utc_or_none(agent_state.last_seen_at)
        if last_seen_at is None:
            return "heartbeat_missing"
        if last_seen_at < now - timedelta(seconds=self.node_state_stale_after_sec):
            return "heartbeat_stale"
        return None


def get_route_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> RouteService:
    return RouteService(session)
