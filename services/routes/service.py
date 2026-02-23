from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import NodeRole
from services.routes.repository import RouteRepository, TransportProfileRepository
from services.routes.schemas import (
    RouteCreateData,
    RouteCreateIn,
    RouteHealthAction,
    RouteHealthStatus,
    RouteHealthUpdateIn,
    RouteOut,
    RouteReactivationUpdate,
    RouteStateUpdate,
    RouteWarmupTickOut,
    ProfileReactivationUpdate,
    TransportProfileCreateIn,
    TransportProfileOut,
)
from shared.database.session import AsyncDatabase


class RouteService:
    WARMUP_STAGES: list[tuple[int, int]] = [
        (10, 30),
        (25, 60),
    ]

    def __init__(self, session: AsyncSession):
        self.session = session
        self.node_repository = VpnNodeRepository(session)
        self.transport_repository = TransportProfileRepository(session)
        self.route_repository = RouteRepository(session)

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
        protocol = payload.protocol.strip().lower()
        network = payload.network.strip().lower()
        security = payload.security.strip().lower()
        if protocol != "vless":
            raise HTTPException(status_code=422, detail=f"Unsupported protocol: {protocol}")

        flow = payload.flow.strip() if isinstance(payload.flow, str) else payload.flow
        reality_public_key = payload.reality_public_key.strip() if payload.reality_public_key else None
        reality_short_id = payload.reality_short_id.strip() if payload.reality_short_id else None
        reality_server_name = payload.reality_server_name.strip() if payload.reality_server_name else None
        grpc_service_name = payload.grpc_service_name.strip() if payload.grpc_service_name else None

        if security == "reality":
            if network != "tcp":
                raise HTTPException(status_code=422, detail="reality transport requires network=tcp")
            if not reality_public_key or not reality_short_id or not reality_server_name:
                raise HTTPException(
                    status_code=422,
                    detail="reality transport requires reality_public_key, reality_short_id and reality_server_name",
                )
            if grpc_service_name:
                raise HTTPException(status_code=422, detail="reality transport does not support grpc_service_name")
        elif security == "tls":
            if network not in {"grpc", "ws"}:
                raise HTTPException(status_code=422, detail="tls transport supports only network=grpc or network=ws")
            if reality_public_key or reality_short_id or reality_server_name:
                raise HTTPException(
                    status_code=422,
                    detail="tls transport does not support reality_* fields",
                )
            if flow:
                raise HTTPException(status_code=422, detail="tls transport does not support flow")
            if network == "grpc":
                grpc_service_name = grpc_service_name or "vl"
            elif grpc_service_name:
                raise HTTPException(status_code=422, detail="ws transport does not support grpc_service_name")
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported security: {security}")

        return TransportProfileCreateIn(
            name=payload.name,
            protocol=protocol,
            network=network,
            security=security,
            flow=flow,
            reality_public_key=reality_public_key,
            reality_short_id=reality_short_id,
            reality_server_name=reality_server_name,
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
        if node.role != NodeRole.backend.value:
            raise HTTPException(status_code=409, detail="Route node role must be backend")

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
            resolved_effective_weight = self._stage_weight(payload.base_weight, 0)

        create_payload = RouteCreateData(
            name=payload.name,
            node_id=payload.node_id,
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
            updated = await self.route_repository.update_by_id(
                existing.id,
                update_payload.model_dump(),
            )
            if not updated:
                raise HTTPException(status_code=500, detail="Failed to create route")
            return RouteOut.model_validate(updated)

        created = await self.route_repository.create(create_payload.model_dump())
        return RouteOut.model_validate(created)

    async def list_routes(
            self,
            *,
            node_id: UUID | None = None,
            limit: int = 200,
    ) -> list[RouteOut]:
        rows = await self.route_repository.list_active(node_id=node_id, limit=limit)
        return [RouteOut.model_validate(row) for row in rows]

    async def update_route_health(
            self,
            route_id: UUID,
            payload: RouteHealthUpdateIn,
    ) -> RouteOut:
        route = await self.route_repository.get_by_id(route_id)
        if not route or not route.is_active:
            raise HTTPException(status_code=404, detail="Route not found")

        now = datetime.now(timezone.utc)
        status = route.health_status
        effective_weight = route.effective_weight
        cooldown_until = route.cooldown_until
        warmup_stage = route.warmup_stage
        warmup_started_at = route.warmup_started_at

        if payload.action == RouteHealthAction.block:
            status = RouteHealthStatus.blocked.value
            effective_weight = 0
            cooldown_until = now + timedelta(hours=payload.cooldown_hours)
            warmup_stage = None
            warmup_started_at = None
        elif payload.action == RouteHealthAction.recover:
            if cooldown_until is not None and cooldown_until > now:
                raise HTTPException(status_code=409, detail="Route is still in cooldown")
            status = RouteHealthStatus.warming_up.value
            warmup_stage = 0
            warmup_started_at = now
            effective_weight = self._stage_weight(route.base_weight, 0)
            cooldown_until = None
        elif payload.action == RouteHealthAction.set_healthy:
            status = RouteHealthStatus.healthy.value
            effective_weight = route.base_weight
            cooldown_until = None
            warmup_stage = None
            warmup_started_at = None
        elif payload.action == RouteHealthAction.set_degraded:
            status = RouteHealthStatus.degraded.value
            effective_weight = max(1, min(route.base_weight, route.base_weight // 2))
            cooldown_until = None
            warmup_stage = None
            warmup_started_at = None
        elif payload.action == RouteHealthAction.set_suspected:
            status = RouteHealthStatus.suspected.value
            effective_weight = max(1, min(route.base_weight, route.base_weight // 3))
            cooldown_until = None
            warmup_stage = None
            warmup_started_at = None

        updated = await self.route_repository.update_by_id(
            item_id=route.id,
            data=RouteStateUpdate(
                health_status=RouteHealthStatus(status),
                effective_weight=effective_weight,
                cooldown_until=cooldown_until,
                warmup_stage=warmup_stage,
                warmup_started_at=warmup_started_at,
                updated_at=now,
            ).model_dump(),
        )
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update route health")
        return RouteOut.model_validate(updated)

    async def advance_warmup(self) -> RouteWarmupTickOut:
        now = datetime.now(timezone.utc)
        routes = await self.route_repository.list_warming_up()
        processed = 0
        advanced = 0
        finalized = 0

        for route in routes:
            processed += 1
            stage = route.warmup_stage
            started = route.warmup_started_at
            if stage is None or started is None:
                updated = await self.route_repository.update_by_id(
                    item_id=route.id,
                    data=RouteStateUpdate(
                        health_status=RouteHealthStatus.healthy,
                        effective_weight=route.base_weight,
                        cooldown_until=None,
                        warmup_stage=None,
                        warmup_started_at=None,
                        updated_at=now,
                    ).model_dump(),
                )
                if updated:
                    finalized += 1
                continue

            if stage >= len(self.WARMUP_STAGES):
                updated = await self.route_repository.update_by_id(
                    item_id=route.id,
                    data=RouteStateUpdate(
                        health_status=RouteHealthStatus.healthy,
                        effective_weight=route.base_weight,
                        cooldown_until=None,
                        warmup_stage=None,
                        warmup_started_at=None,
                        updated_at=now,
                    ).model_dump(),
                )
                if updated:
                    finalized += 1
                continue

            _, hold_minutes = self.WARMUP_STAGES[stage]
            elapsed = (now - started).total_seconds() / 60
            if elapsed < hold_minutes:
                continue

            next_stage = stage + 1
            if next_stage >= len(self.WARMUP_STAGES):
                updated = await self.route_repository.update_by_id(
                    item_id=route.id,
                    data=RouteStateUpdate(
                        health_status=RouteHealthStatus.healthy,
                        effective_weight=route.base_weight,
                        cooldown_until=None,
                        warmup_stage=None,
                        warmup_started_at=None,
                        updated_at=now,
                    ).model_dump(),
                )
                if updated:
                    finalized += 1
                continue

            updated = await self.route_repository.update_by_id(
                item_id=route.id,
                data=RouteStateUpdate(
                    health_status=RouteHealthStatus.warming_up,
                    effective_weight=self._stage_weight(route.base_weight, next_stage),
                    cooldown_until=None,
                    warmup_stage=next_stage,
                    warmup_started_at=now,
                    updated_at=now,
                ).model_dump(),
            )
            if updated:
                advanced += 1

        return RouteWarmupTickOut(
            processed=processed,
            advanced=advanced,
            finalized=finalized,
        )

    def _stage_weight(self, base_weight: int, stage: int) -> int:
        if base_weight <= 0:
            return 0
        if stage >= len(self.WARMUP_STAGES):
            return base_weight
        stage_weight, _ = self.WARMUP_STAGES[stage]
        return min(base_weight, stage_weight)


def get_route_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> RouteService:
    return RouteService(session)
