from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.artifacts.exceptions import ArtifactStoreError
from services.artifacts.models import ProfileArtifact
from services.artifacts.schemas import (
    ArtifactRoutesBootstrapIn,
    ArtifactRoutesBootstrapOut,
    ProfileArtifactCreate,
    ProfileArtifactPublishIn,
)
from services.artifacts.repository import ProfileArtifactRepository
from services.nodes.repository import VpnNodeRepository
from services.routes.repository import RouteRepository, TransportProfileRepository
from services.routes.schemas import (
    RouteCreateData,
    RouteHealthStatus,
    RouteReactivationUpdate,
    ProfileReactivationUpdate,
)
from services.routes.state_machine import resolve_bootstrap_recovery
from shared.database.session import AsyncDatabase
from shared.profiles.artifact_mapper import ArtifactProfileMapper


class ProfileArtifactService:
    def __init__(self, session: AsyncSession):
        self.repository = ProfileArtifactRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.transport_repository = TransportProfileRepository(session)
        self.route_repository = RouteRepository(session)
        self.session = session

    async def publish(self, data: ProfileArtifactPublishIn) -> ProfileArtifact:
        payload = json.dumps(data.artifact, sort_keys=True).encode()
        checksum = hashlib.sha256(payload).hexdigest()

        version = await self.repository.get_latest_version() + 1

        await self.repository.deactivate_all()

        artifact = await self.repository.create(
            ProfileArtifactCreate(
                version=version,
                checksum=checksum,
                artifact=data.artifact
            ).model_dump()
        )

        return artifact

    async def get_active(self):
        artifact = await self.repository.get_active()
        if not artifact:
            raise ArtifactStoreError("No active profiles artifact")
        return artifact

    async def bootstrap_routes_from_active_artifact(
            self,
            payload: ArtifactRoutesBootstrapIn,
    ) -> ArtifactRoutesBootstrapOut:
        artifact = await self.get_active()

        mapper = ArtifactProfileMapper(
            include_reality_tcp=payload.include_reality_tcp,
            include_ws_tls=payload.include_ws_tls,
            default_reality_port=payload.default_reality_port,
            default_ws_port=payload.default_ws_port,
            profile_port_overrides=payload.profile_port_overrides,
        )
        projected = mapper.map(artifact.artifact)
        desired_profiles = projected.desired_profiles
        skipped_profiles = projected.skipped_profiles
        profiles_total = projected.profiles_total
        if not desired_profiles:
            raise HTTPException(
                status_code=422,
                detail="No eligible profiles in active artifact for bootstrap policy",
            )

        backends = await self._resolve_target_backends(backend_node_ids=payload.backend_node_ids)
        if not backends:
            raise HTTPException(
                status_code=409,
                detail="No eligible nodes for routes bootstrap",
            )
        routes_total = len(desired_profiles) * len(backends)
        self._validate_matrix_expectations(
            expected_backends_selected=payload.expected_backends_selected,
            actual_backends_selected=len(backends),
            expected_profiles_selected=payload.expected_profiles_selected,
            actual_profiles_selected=len(desired_profiles),
            expected_routes_total=payload.expected_routes_total,
            actual_routes_total=routes_total,
        )

        transport_created = 0
        transport_updated = 0
        transport_reactivated = 0

        transport_names = [profile.name for profile in desired_profiles]
        existing_transports = await self.transport_repository.list_by_names(transport_names)
        transport_by_name = {row.name: row for row in existing_transports}

        for profile in desired_profiles:
            existing = transport_by_name.get(profile.name)
            desired_transport = ProfileReactivationUpdate(
                name=profile.name,
                protocol=profile.protocol,
                network=profile.network,
                security=profile.security,
                flow=profile.flow,
                reality_public_key=profile.reality_public_key,
                reality_short_id=profile.reality_short_id,
                reality_server_name=profile.reality_server_name,
                tls_fingerprint=profile.tls_fingerprint,
                grpc_service_name=profile.grpc_service_name,
                port=profile.port,
                is_active=True,
            )
            if existing is None:
                transport_created += 1
                if payload.dry_run:
                    continue
                created = await self.transport_repository.create(desired_transport.model_dump())
                transport_by_name[profile.name] = created
                continue

            has_transport_changes = self._transport_needs_update(
                existing=existing,
                desired=desired_transport,
            )
            if not existing.is_active:
                transport_reactivated += 1

            if not has_transport_changes and existing.is_active:
                continue

            transport_updated += 1
            if payload.dry_run:
                continue
            updated = await self.transport_repository.update_by_id(
                existing.id,
                desired_transport.model_dump(),
            )
            if updated is not None:
                transport_by_name[profile.name] = updated

        route_created = 0
        route_updated = 0
        route_reactivated = 0
        route_names = self._build_route_names(backends=backends, transport_names=transport_names)
        existing_routes = await self.route_repository.list_by_names(route_names)
        route_by_name = {row.name: row for row in existing_routes}

        for backend in backends:
            for transport_name in transport_names:
                route_name = self._build_route_name(
                    backend_name=backend.name,
                    transport_name=transport_name,
                )
                existing = route_by_name.get(route_name)
                transport = transport_by_name.get(transport_name)
                transport_id: UUID | None = None if transport is None else transport.id

                if existing is None:
                    route_created += 1
                    if payload.dry_run:
                        continue
                    if transport_id is None:
                        continue
                    route_create = RouteCreateData(
                        name=route_name,
                        node_id=backend.id,
                        transport_profile_id=transport_id,
                        health_status=RouteHealthStatus.healthy,
                        base_weight=payload.route_base_weight,
                        effective_weight=payload.route_base_weight,
                        cooldown_until=None,
                        warmup_stage=None,
                        warmup_started_at=None,
                        is_active=True,
                    )
                    created = await self.route_repository.create(route_create.model_dump())
                    route_by_name[route_name] = created
                    continue

                route_update = self._build_route_update(
                    existing=existing,
                    backend_id=backend.id,
                    transport_profile_id=transport_id,
                    route_base_weight=payload.route_base_weight,
                    recover_unhealthy_routes=payload.recover_unhealthy_routes,
                )
                if route_update is None:
                    continue

                if not existing.is_active:
                    route_reactivated += 1
                route_updated += 1
                if payload.dry_run:
                    continue
                await self.route_repository.update_by_id(
                    existing.id,
                    route_update.model_dump(),
                )

        return ArtifactRoutesBootstrapOut(
            artifact_version=artifact.version,
            dry_run=payload.dry_run,
            backends_selected=len(backends),
            profiles_total=profiles_total,
            profiles_selected=len(desired_profiles),
            routes_total=routes_total,
            transport_profiles_created=transport_created,
            transport_profiles_updated=transport_updated,
            transport_profiles_reactivated=transport_reactivated,
            routes_created=route_created,
            routes_updated=route_updated,
            routes_reactivated=route_reactivated,
            skipped_profiles=skipped_profiles,
        )

    @staticmethod
    def _transport_needs_update(
            *,
            existing,
            desired: ProfileReactivationUpdate,
    ) -> bool:
        if existing.name != desired.name:
            return True
        if existing.protocol != desired.protocol:
            return True
        if existing.network != desired.network:
            return True
        if existing.security != desired.security:
            return True
        if existing.flow != desired.flow:
            return True
        if existing.reality_public_key != desired.reality_public_key:
            return True
        if existing.reality_short_id != desired.reality_short_id:
            return True
        if existing.reality_server_name != desired.reality_server_name:
            return True
        if existing.tls_fingerprint != desired.tls_fingerprint:
            return True
        if existing.grpc_service_name != desired.grpc_service_name:
            return True
        if int(existing.port) != int(desired.port):
            return True
        return not bool(existing.is_active)

    @staticmethod
    def _build_route_update(
            *,
            existing,
            backend_id: UUID,
            transport_profile_id: UUID | None,
            route_base_weight: int,
            recover_unhealthy_routes: bool,
    ) -> RouteReactivationUpdate | None:
        target_transport_id = transport_profile_id or existing.transport_profile_id
        structural_change = (
                existing.node_id != backend_id
                or existing.transport_profile_id != target_transport_id
        )
        was_inactive = not bool(existing.is_active)
        base_weight_changed = int(existing.base_weight) != int(route_base_weight)

        try:
            current_status = RouteHealthStatus(str(existing.health_status))
        except ValueError:
            current_status = RouteHealthStatus.healthy

        effective_weight = int(existing.effective_weight)
        cooldown_until = existing.cooldown_until
        warmup_stage = existing.warmup_stage
        warmup_started_at = existing.warmup_started_at

        if base_weight_changed and not (structural_change or was_inactive):
            effective_weight = min(max(0, effective_weight), int(route_base_weight))

        if structural_change or was_inactive:
            current_status = RouteHealthStatus.healthy
            effective_weight = int(route_base_weight)
            cooldown_until = None
            warmup_stage = None
            warmup_started_at = None
        elif recover_unhealthy_routes and (
                current_status in {
                    RouteHealthStatus.blocked,
                    RouteHealthStatus.degraded,
                    RouteHealthStatus.suspected,
                }
                or effective_weight <= 0
        ):
            bootstrap_state = resolve_bootstrap_recovery(
                route_base_weight=route_base_weight,
                now=datetime.now(timezone.utc),
            )
            current_status = bootstrap_state["health_status"]
            effective_weight = bootstrap_state["effective_weight"]
            cooldown_until = bootstrap_state["cooldown_until"]
            warmup_stage = bootstrap_state["warmup_stage"]
            warmup_started_at = bootstrap_state["warmup_started_at"]

        desired = RouteReactivationUpdate(
            name=existing.name,
            node_id=backend_id,
            transport_profile_id=target_transport_id,
            health_status=current_status,
            base_weight=int(route_base_weight),
            effective_weight=max(0, min(int(route_base_weight), int(effective_weight))),
            cooldown_until=cooldown_until,
            warmup_stage=warmup_stage,
            warmup_started_at=warmup_started_at,
            is_active=True,
        )

        no_changes = (
                existing.name == desired.name
                and existing.node_id == desired.node_id
                and existing.transport_profile_id == desired.transport_profile_id
                and str(existing.health_status) == desired.health_status.value
                and int(existing.base_weight) == int(desired.base_weight)
                and int(existing.effective_weight) == int(desired.effective_weight)
                and existing.cooldown_until == desired.cooldown_until
                and existing.warmup_stage == desired.warmup_stage
                and existing.warmup_started_at == desired.warmup_started_at
                and bool(existing.is_active) == bool(desired.is_active)
        )
        if no_changes:
            return None
        return desired

    async def _resolve_target_backends(self, *, backend_node_ids: list[UUID] | None):
        if backend_node_ids:
            rows = await self.node_repository.list_by_ids(backend_node_ids)
            by_id = {row.id: row for row in rows}
            missing = [str(node_id) for node_id in backend_node_ids if node_id not in by_id]
            if missing:
                raise HTTPException(
                    status_code=404,
                    detail=f"Backend nodes not found: {', '.join(missing)}",
                )
            ordered = [by_id[node_id] for node_id in backend_node_ids]
        else:
            ordered = list(await self.node_repository.list_public())
            ordered.sort(key=lambda row: row.name)

        return [
            row
            for row in ordered
            if row.is_active and row.is_enabled and not row.is_draining
        ]

    def _build_route_names(self, *, backends: list, transport_names: list[str]) -> list[str]:
        return [
            self._build_route_name(backend_name=backend.name, transport_name=transport_name)
            for backend in backends
            for transport_name in transport_names
        ]

    def _build_route_name(self, *, backend_name: str, transport_name: str) -> str:
        base = f"auto-{backend_name}-{transport_name}"
        return ArtifactProfileMapper.normalize_name(key=base, max_len=100)

    @staticmethod
    def _validate_matrix_expectations(
            *,
            expected_backends_selected: int | None,
            actual_backends_selected: int,
            expected_profiles_selected: int | None,
            actual_profiles_selected: int,
            expected_routes_total: int | None,
            actual_routes_total: int,
    ) -> None:
        if expected_backends_selected is not None and expected_backends_selected != actual_backends_selected:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Bootstrap matrix mismatch: "
                    f"expected_backends_selected={expected_backends_selected}, "
                    f"actual_backends_selected={actual_backends_selected}"
                ),
            )
        if expected_profiles_selected is not None and expected_profiles_selected != actual_profiles_selected:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Bootstrap matrix mismatch: "
                    f"expected_profiles_selected={expected_profiles_selected}, "
                    f"actual_profiles_selected={actual_profiles_selected}"
                ),
            )
        if expected_routes_total is not None and expected_routes_total != actual_routes_total:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Bootstrap matrix mismatch: "
                    f"expected_routes_total={expected_routes_total}, "
                    f"actual_routes_total={actual_routes_total}"
                ),
            )


def get_profile_artifact_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> ProfileArtifactService:
    return ProfileArtifactService(session)
