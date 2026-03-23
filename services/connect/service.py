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
from services.placements.transport import NodeAgentPlacementTransport
from shared.profiles.builder import VlessUriBuilder
from shared.profiles.constants import WS_TLS_DEFAULT_PATH
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
        self.node_agent_transport = NodeAgentPlacementTransport(session)
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
        key_transport = self._normalize_key_transport(getattr(key, "transport", None))
        desired_replicas = max(1, min(10, int(payload.max_routes)))
        preferred_node_id, placement, allowed_backend_ids = await self._ensure_backend_placements_for_key(
            key_id=key_id,
            preferred_region=payload.preferred_region,
            desired_replicas=desired_replicas,
            key_transport=key_transport,
        )

        max_fetch = max(payload.max_routes * 4, 10)
        allowed_backend_ids_sorted = sorted(allowed_backend_ids, key=str)
        route_rows = await self.route_repository.list_resolved_active(
            preferred_node_id=preferred_node_id,
            preferred_region=payload.preferred_region,
            limit=max_fetch,
            backend_node_ids=allowed_backend_ids_sorted,
            node_seen_after=self._resolved_route_node_seen_after(),
        )
        entry_nodes_by_id = await self._entry_nodes_by_id(route_rows=route_rows)

        resolved_routes: list[ResolvedRouteInternal] = []
        for route, node, transport_profile in route_rows:
            backend_node_id = self._as_uuid(node.id)
            if backend_node_id not in allowed_backend_ids:
                continue
            entry_node_id = self._route_entry_node_id(route)
            entry_node = entry_nodes_by_id.get(entry_node_id) if entry_node_id is not None else None
            transport_security = transport_profile.security
            transport_network = transport_profile.network
            if not self._is_route_compatible_with_key_transport(
                key_transport=key_transport,
                transport_security=transport_security,
                transport_network=transport_network,
            ):
                continue
            uri = self._build_route_uri(
                client_id=key.client_id,
                backend_node=node,
                public_node=entry_node,
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
                        entry_node_id=entry_node_id,
                        transport_profile_id=transport_profile_id,
                        health_status=route.health_status,
                        effective_weight=route.effective_weight,
                        uri=uri,
                    ),
                    transport_security=transport_security,
                    transport_network=transport_network,
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
            key_transport: str | None,
    ) -> tuple[UUID, UserPlacement, set[UUID]]:
        desired_replicas = max(1, min(10, int(desired_replicas)))
        all_placements = await self.placement_repository.list_by_key_id(
            key_id=key_id,
            active_only=True,
            desired_state=PlacementDesiredState.active.value,
        )
        placements_by_backend: dict[UUID, UserPlacement] = {
            placement.backend_node_id: placement for placement in all_placements
        }
        synced_placements = [
            placement for placement in all_placements if self._is_placement_synced(placement)
        ]
        synced_by_backend: dict[UUID, UserPlacement] = {
            placement.backend_node_id: placement for placement in synced_placements
        }

        try:
            candidate_nodes = await self.routing_service.select_nodes(
                preferred_region=preferred_region,
            )
        except Exception:
            logger_connect.exception(
                "connect_routeset_select_nodes_failed",
                key_id=str(key_id),
                preferred_region=preferred_region,
            )
            candidate_nodes = []
        backend_ids_with_entry_routes = set(
            await self.route_repository.list_backend_ids_with_entry_routes(
                key_transport=key_transport,
            )
        )
        candidate_nodes = [
            node
            for node in candidate_nodes
            if self._node_has_required_public_host(
                node=node,
                key_transport=key_transport,
                allow_entry_route=self._as_uuid(str(node.id)) in backend_ids_with_entry_routes,
            )
        ]
        if not candidate_nodes and not placements_by_backend:
            fallback = await self._select_backend(
                preferred_region=preferred_region,
                key_transport=key_transport,
            )
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
                await self.node_agent_transport.enqueue_for_placement_ids([created.id])
                placements_by_backend[node_id] = created
            target_node_ids = [self._as_uuid(str(node.id)) for node in target_nodes]
        else:
            target_node_ids = []

        preferred_placement: UserPlacement | None = None
        for node_id in target_node_ids:
            preferred_placement = synced_by_backend.get(node_id) or placements_by_backend.get(node_id)
            if preferred_placement is not None:
                break
        if preferred_placement is None and synced_placements and not target_node_ids:
            preferred_placement = synced_placements[0]
        if preferred_placement is None and placements_by_backend:
            preferred_placement = next(iter(placements_by_backend.values()))
        if preferred_placement is None:
            raise HTTPException(status_code=503, detail="Node placement sync pending")

        preferred_backend_id = self._as_uuid(preferred_placement.backend_node_id)
        allowed_backend_ids = set(target_node_ids) if target_node_ids else set(placements_by_backend.keys())
        if not allowed_backend_ids:
            raise HTTPException(status_code=503, detail="Node placement sync pending")
        return preferred_backend_id, preferred_placement, allowed_backend_ids

    def _resolved_route_node_seen_after(self) -> datetime:
        node_agent_settings = getattr(self.settings, "node_agent", None)
        stale_after_raw = getattr(node_agent_settings, "stale_after_sec", 90)
        stale_after_sec = max(30, int(stale_after_raw)) * 3
        return datetime.now(timezone.utc) - timedelta(seconds=stale_after_sec)

    async def _list_active_placements_for_key(self, *, key_id: UUID) -> list[UserPlacement]:
        rows = await self.placement_repository.list_by_key_id(
            key_id=key_id,
            active_only=True,
            desired_state=PlacementDesiredState.active.value,
        )
        return [
            row
            for row in rows
            if row.backend_node_id is not None and self._is_placement_synced(row)
        ]

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
            transport=VpnTransport.reality,
            client_id=str(uuid4()),
            valid_until=valid_until,
            traffic_limit_mb=payload.traffic_limit_mb,
            is_revoked=False,
        )
        return await self.key_repository.create(key_internal.model_dump())

    async def _select_backend(
            self,
            *,
            preferred_region: str | None,
            key_transport: str | None = None,
    ) -> VpnNode:
        candidates = await self.routing_service.select_nodes(
            preferred_region=preferred_region,
        )
        backend_ids_with_entry_routes = set(
            await self.route_repository.list_backend_ids_with_entry_routes(
                key_transport=key_transport,
            )
        )
        for candidate in candidates:
            if self._node_has_required_public_host(
                node=candidate,
                key_transport=key_transport,
                allow_entry_route=self._as_uuid(str(candidate.id)) in backend_ids_with_entry_routes,
            ):
                return candidate
        raise HTTPException(status_code=503, detail="No eligible node available")

    @staticmethod
    def _is_placement_synced(placement: UserPlacement) -> bool:
        applied_state = getattr(placement, "applied_state", "applied")
        if not isinstance(applied_state, str):
            applied_state = "applied"
        applied_version = getattr(placement, "applied_version", placement.op_version)
        if not isinstance(applied_version, int):
            applied_version = placement.op_version
        return applied_state == "applied" and applied_version == placement.op_version

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
            backend_node: VpnNode | None = None,
            node: VpnNode | None = None,
            transport_profile,
            public_node: VpnNode | None = None,
    ) -> str | None:
        backend_node = backend_node or node
        if backend_node is None:
            return None
        domain = self._resolve_route_host_for_transport(
            backend_node=backend_node,
            public_node=public_node,
            transport_profile=transport_profile,
        )
        if not domain:
            return None
        display_node = public_node or backend_node
        node_display_name = format_node_display_name(
            node_name=str(display_node.name),
            region=backend_node.region,
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
            region=backend_node.region,
        )
        if profile is None:
            return None

        node_public = NodePublic(
            domain=domain,
            port=transport_profile.port,
            remark=node_display_name,
            region=backend_node.region,
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
                    path=WS_TLS_DEFAULT_PATH,
                    host=fallback_domain,
                    sni=fallback_domain,
                ),
            )

        return None

    def _resolve_ws_public_host(self, node: VpnNode, *, prefer_node_domain: bool = False) -> str:
        if prefer_node_domain:
            node_domain = (node.public_domain or "").strip()
            if node_domain:
                return node_domain
        edge_domain = self.settings.edge.public_domain
        if edge_domain:
            return edge_domain
        return node.public_domain

    @staticmethod
    def _resolve_reality_host(node: VpnNode) -> str:
        return node.reality_ip or ""

    def _resolve_route_host_for_transport(
            self,
            *,
            backend_node: VpnNode,
            transport_profile,
            public_node: VpnNode | None = None,
    ) -> str:
        network = transport_profile.network
        security = transport_profile.security
        visible_node = public_node or backend_node
        if security == "reality" and network == "tcp":
            return self._resolve_reality_host(visible_node)
        return self._resolve_ws_public_host(
            visible_node,
            prefer_node_domain=public_node is not None,
        )

    def _node_has_required_public_host(
            self,
            *,
            node: VpnNode,
            key_transport: str | None,
            allow_entry_route: bool = False,
    ) -> bool:
        if allow_entry_route:
            return True
        if key_transport == VpnTransport.reality.value:
            return bool(self._resolve_reality_host(node))
        if key_transport == VpnTransport.tcp.value:
            return False
        if key_transport == VpnTransport.ws.value:
            return bool(self._resolve_ws_public_host(node))
        return bool(self._resolve_reality_host(node) or self._resolve_ws_public_host(node))

    @staticmethod
    def _normalize_key_transport(raw_transport: object) -> str | None:
        if not isinstance(raw_transport, str):
            return None
        normalized = raw_transport.strip().lower()
        return normalized or None

    @staticmethod
    def _is_route_compatible_with_key_transport(
            *,
            key_transport: str | None,
            transport_security: str,
            transport_network: str,
    ) -> bool:
        if key_transport == VpnTransport.reality.value:
            return transport_security == "reality" and transport_network == "tcp"
        if key_transport == VpnTransport.tcp.value:
            return False
        if key_transport == VpnTransport.ws.value:
            return transport_security == "tls" and transport_network == "ws"
        if key_transport == VpnTransport.xhttp.value:
            return transport_security == "tls" and transport_network == "xhttp"
        return True

    async def _entry_nodes_by_id(
            self,
            *,
            route_rows: list[tuple[object, VpnNode, object]],
    ) -> dict[UUID, VpnNode]:
        entry_ids = [
            entry_node_id
            for route, _node, _transport_profile in route_rows
            for entry_node_id in [self._route_entry_node_id(route)]
            if entry_node_id is not None
        ]
        if not entry_ids:
            return {}
        rows = await self.node_repository.list_by_ids(list(dict.fromkeys(entry_ids)))
        return {self._as_uuid(row.id): row for row in rows}

    def _route_entry_node_id(self, route) -> UUID | None:
        raw = getattr(route, "entry_node_id", None)
        if isinstance(raw, UUID):
            return raw
        if isinstance(raw, str):
            return UUID(raw)
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
