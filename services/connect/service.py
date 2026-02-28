from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.connect.cache_keys import connect_telemetry_allowed_routes_key
from services.connect.policy import build_connect_refresh_policy
from services.connect.schemas import (
    ConnectRouteOut,
    ConnectRouteSetIn,
    ConnectRouteSetOut,
    ResolvedRouteInternal,
)
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import NodeRole
from services.placements.model import UserPlacement
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.routes.repository import RouteRepository
from services.routing.selector import RouteSelector
from services.routing.service import RoutingService
from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.keys.schemas import VpnKeyInternalCreate, VpnProtocol, VpnTransport
from shared.database.session import AsyncDatabase
from shared.profiles.builder import VlessUriBuilder
from shared.profiles.schemas import (
    NodePublic,
    ProfileMetadata,
    RealityTcpClientConfig,
    RealityTcpProfile,
    WsTlsClientConfig,
    WsTlsProfile,
)
from shared.profiles.transport import VlessUri
from shared.redis.client import RedisClient, get_redis_client
from shared.utils.node_display import format_node_display_name
from shared.utils.logger import StructuredLogger


logger_connect = StructuredLogger(logging.getLogger("connect-service"))


class ConnectService:
    def __init__(self, session: AsyncSession, redis: RedisClient):
        self.settings = get_settings()
        self.redis = redis
        self.user_repository = UserRepository(session)
        self.key_repository = VpnKeyRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.route_repository = RouteRepository(session)
        self.routing_service = RoutingService(session)
        self.route_selector = RouteSelector[ResolvedRouteInternal](
            get_backend_id=lambda item: item.route.backend_node_id,
            get_transport_key=lambda item: (item.transport_security, item.transport_network),
            get_route_id=lambda item: item.route.route_id,
        )

    async def connect_routeset(self, payload: ConnectRouteSetIn) -> ConnectRouteSetOut:
        user = await self.user_repository.get_by_id(payload.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        key = await self._resolve_routeset_key(payload=payload)
        key_id = self._as_uuid(key.id)
        desired_replicas = max(1, min(10, int(payload.max_routes)))
        preferred_node_id, placement, allowed_backend_ids = await self._ensure_backend_placements_for_key(
            key_id=key_id,
            preferred_region=payload.preferred_region,
            desired_replicas=desired_replicas,
        )

        max_fetch = max(payload.max_routes * 4, 10)
        route_rows = await self.route_repository.list_resolved_active(
            preferred_node_id=preferred_node_id,
            preferred_region=payload.preferred_region,
            limit=max_fetch,
        )

        resolved_routes: list[ResolvedRouteInternal] = []
        for route, node, transport_profile in route_rows:
            backend_node_id = self._as_uuid(node.id)
            if backend_node_id not in allowed_backend_ids:
                continue
            uri = self._build_route_uri(
                client_id=key.client_id,
                node=node,
                transport_profile=transport_profile,
            )
            if uri is None:
                continue
            route_id = self._as_uuid(route.id)
            transport_profile_id = self._as_uuid(transport_profile.id)
            resolved_routes.append(
                ResolvedRouteInternal(
                    route=ConnectRouteOut(
                        route_id=route_id,
                        route_name=route.name,
                        backend_node_id=backend_node_id,
                        transport_profile_id=transport_profile_id,
                        health_status=route.health_status,
                        effective_weight=route.effective_weight,
                        uri=uri,
                    ),
                    transport_security=(transport_profile.security or "").strip().lower(),
                    transport_network=(transport_profile.network or "").strip().lower(),
                )
            )
        routes = self.route_selector.select(
            routes=resolved_routes,
            preferred_backend_id=preferred_node_id,
            max_routes=payload.max_routes,
        )

        if not routes:
            raise HTTPException(status_code=503, detail="No available routes")

        placement_id = self._as_uuid(placement.id)
        refresh_policy = build_connect_refresh_policy(self.settings.routes)
        route_out_items = [item.route for item in routes]
        await self._cache_allowed_telemetry_routes(
            key_id=key_id,
            route_ids=[item.route_id for item in route_out_items],
            ttl_sec=refresh_policy.max_cache_age_sec,
        )
        return ConnectRouteSetOut(
            key_id=key_id,
            client_id=key.client_id,
            placement_id=placement_id,
            placement_op_version=placement.op_version,
            config_version=placement.op_version,
            selection_strategy="ordered_fallback",
            refresh_interval_sec=refresh_policy.refresh_interval_sec,
            max_cache_age_sec=refresh_policy.max_cache_age_sec,
            backoff_steps_sec=refresh_policy.backoff_steps_sec,
            routes=route_out_items,
        )

    async def _ensure_backend_placements_for_key(
            self,
            *,
            key_id: UUID,
            preferred_region: str | None,
            desired_replicas: int,
    ) -> tuple[UUID, UserPlacement, set[UUID]]:
        desired_replicas = max(1, min(10, int(desired_replicas)))
        placements = await self._list_active_placements_for_key(key_id=key_id)
        placements_by_backend: dict[UUID, UserPlacement] = {
            placement.backend_node_id: placement for placement in placements
        }

        try:
            candidate_nodes = await self.routing_service.select_nodes(
                preferred_region=preferred_region,
                role=NodeRole.backend.value,
            )
        except Exception:
            logger_connect.exception(
                "connect_routeset_select_nodes_failed",
                key_id=str(key_id),
                preferred_region=preferred_region,
            )
            candidate_nodes = []
        edge_domain = self.settings.edge.public_domain.strip()
        candidate_nodes = [
            node
            for node in candidate_nodes
            if edge_domain or str(getattr(node, "public_domain", "") or "").strip()
        ]
        if not candidate_nodes and not placements_by_backend:
            fallback = await self._select_backend(preferred_region=preferred_region)
            candidate_nodes = [fallback]

        if candidate_nodes:
            target_nodes = candidate_nodes[:desired_replicas]
            for node in target_nodes:
                node_id = self._as_uuid(str(node.id))
                if node_id in placements_by_backend:
                    continue
                created = await self.placement_repository.upsert_set_pending(
                    key_id=key_id,
                    backend_node_id=node_id,
                    desired_state=PlacementDesiredState.active.value,
                    sticky_until=None,
                    last_migration_reason="connect_replica",
                )
                placements_by_backend[node_id] = created

        preferred_placement: UserPlacement | None = None
        for node in candidate_nodes:
            node_id = self._as_uuid(str(node.id))
            preferred_placement = placements_by_backend.get(node_id)
            if preferred_placement is not None:
                break
        if preferred_placement is None and placements:
            preferred_placement = placements[0]
        if preferred_placement is None:
            raise HTTPException(status_code=500, detail="Failed to select preferred placement")

        preferred_backend_id = self._as_uuid(preferred_placement.backend_node_id)
        allowed_backend_ids = set(placements_by_backend.keys())
        if not allowed_backend_ids:
            raise HTTPException(status_code=500, detail="No active placements available")
        return preferred_backend_id, preferred_placement, allowed_backend_ids

    async def _list_active_placements_for_key(self, *, key_id: UUID) -> list[UserPlacement]:
        list_by_key = getattr(self.placement_repository, "list_by_key_id", None)
        if callable(list_by_key):
            try:
                rows = await list_by_key(
                    key_id=key_id,
                    active_only=True,
                    desired_state=PlacementDesiredState.active.value,
                )
            except TypeError:
                rows = await list_by_key(
                    key_id=key_id,
                    active_only=True,
                )
            normalized_rows = self._normalize_placements(rows)
            if normalized_rows:
                return normalized_rows

        get_by_key = getattr(self.placement_repository, "get_by_key_id", None)
        if callable(get_by_key):
            row = await get_by_key(key_id=key_id)
            normalized_rows = self._normalize_placements(row)
            if normalized_rows:
                return normalized_rows
        return []

    def _normalize_placements(self, value: Any) -> list[UserPlacement]:
        if value is None:
            return []
        if isinstance(value, list):
            items = value
        elif isinstance(value, tuple):
            items = list(value)
        else:
            items = [value]

        out: list[UserPlacement] = []
        for item in items:
            try:
                backend_node_id = self._as_uuid(getattr(item, "backend_node_id"))
                setattr(item, "backend_node_id", backend_node_id)
                out.append(item)
            except Exception:
                continue
        return out

    async def _resolve_routeset_key(self, *, payload: ConnectRouteSetIn):
        if payload.key_id is not None:
            key = await self.key_repository.get_by_id(payload.key_id)
            if not key:
                raise HTTPException(status_code=404, detail="Key not found")
            if key.user_id != payload.user_id:
                raise HTTPException(status_code=409, detail="Key does not belong to user")
            if key.is_revoked:
                raise HTTPException(status_code=409, detail="Key is revoked")
            return key

        key = await self.key_repository.get_latest_active_for_user(
            user_id=payload.user_id,
            transport=None,
        )
        if key:
            return key

        valid_until = payload.valid_until
        if valid_until is None:
            valid_until = datetime.now(timezone.utc) + timedelta(days=365)

        key_internal = VpnKeyInternalCreate(
            user_id=payload.user_id,
            protocol=VpnProtocol.vless,
            transport=VpnTransport.tcp,
            client_id=str(uuid4()),
            valid_until=valid_until,
            traffic_limit_mb=payload.traffic_limit_mb,
            is_revoked=False,
        )
        return await self.key_repository.create(key_internal.model_dump())

    async def _select_backend(self, *, preferred_region: str | None) -> VpnNode:
        candidates = await self.routing_service.select_nodes(
            preferred_region=preferred_region,
            role=NodeRole.backend.value,
        )
        edge_domain = self.settings.edge.public_domain.strip()
        for candidate in candidates:
            if edge_domain or candidate.public_domain.strip():
                return candidate
        raise HTTPException(status_code=503, detail="No eligible backend node available")

    def _is_backend_eligible(self, node: VpnNode) -> bool:
        if not node.is_active:
            return False
        if not node.is_enabled:
            return False
        if node.is_draining:
            return False
        if node.role != NodeRole.backend.value:
            return False
        return bool((node.internal_wg_ip or "").strip())

    def _as_uuid(self, value: Any) -> UUID:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        raise TypeError(f"Expected UUID-compatible value, got {type(value)!r}")

    def _build_route_uri(
            self,
            *,
            client_id: str,
            node: VpnNode,
            transport_profile,
    ) -> str | None:
        edge_domain = self.settings.edge.public_domain.strip()
        domain = edge_domain or node.public_domain.strip()
        if not domain:
            return None
        node_display_name = format_node_display_name(
            node_name=str(node.name),
            region=node.region,
        )

        network = (transport_profile.network or "").strip().lower()
        security = (transport_profile.security or "").strip().lower()
        if security == "tls" and network == "grpc":
            service_name = (transport_profile.grpc_service_name or "").strip() or "vl"
            fingerprint = (transport_profile.tls_fingerprint or "").strip() or "chrome"
            try:
                return VlessUri(
                    client_id=client_id,
                    host=domain,
                    port=transport_profile.port,
                    query={
                        "type": "grpc",
                        "security": "tls",
                        "encryption": "none",
                        "serviceName": service_name,
                        "sni": domain,
                        "fp": fingerprint,
                    },
                    remark=node_display_name,
                ).render()
            except Exception:
                return None

        profile = self._resolve_profile_from_transport(
            transport_profile=transport_profile,
            fallback_domain=domain,
            region=node.region,
        )
        if profile is None:
            return None

        node_public = NodePublic(
            domain=domain,
            port=transport_profile.port,
            remark=node_display_name,
            region=node.region,
        )
        try:
            return VlessUriBuilder.build(
                client_id=client_id,
                node=node_public,
                profile=profile,
            )
        except Exception:
            return None

    def _resolve_profile_from_transport(
            self,
            *,
            transport_profile,
            fallback_domain: str,
            region: str | None,
    ) -> WsTlsProfile | RealityTcpProfile | None:
        network = (transport_profile.network or "").strip().lower()
        security = (transport_profile.security or "").strip().lower()

        metadata = ProfileMetadata(
            display_name=transport_profile.name or "route-profile",
            region_support=[region] if region else [],
        )

        if security == "reality" and network == "tcp":
            sni = (transport_profile.reality_server_name or "").strip()
            public_key = (transport_profile.reality_public_key or "").strip()
            short_id = (transport_profile.reality_short_id or "").strip()
            fingerprint = (transport_profile.tls_fingerprint or "").strip() or "chrome"
            if not sni or not public_key or not short_id:
                return None
            return RealityTcpProfile(
                metadata=metadata,
                client=RealityTcpClientConfig(
                    sni=sni,
                    flow=transport_profile.flow,
                    fingerprint=fingerprint,
                    public_key=public_key,
                    short_id=short_id,
                ),
            )

        if security == "tls" and network == "ws":
            return WsTlsProfile(
                metadata=metadata,
                client=WsTlsClientConfig(
                    path="/api/v1/stream",
                    host=fallback_domain,
                    sni=fallback_domain,
                ),
            )

        return None

    async def _cache_allowed_telemetry_routes(
            self,
            *,
            key_id: UUID,
            route_ids: list[UUID],
            ttl_sec: int,
    ) -> None:
        if not route_ids:
            return
        cache_key = connect_telemetry_allowed_routes_key(key_id=key_id)
        try:
            await self.redis.client.delete(cache_key)
            await self.redis.client.sadd(cache_key, *[str(route_id) for route_id in route_ids])
            await self.redis.client.expire(cache_key, max(30, int(ttl_sec)))
        except Exception:
            logger_connect.exception(
                "connect_routeset_cache_allowed_routes_failed",
                key_id=str(key_id),
                routes=len(route_ids),
            )

def get_connect_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> ConnectService:
    return ConnectService(session, redis)
