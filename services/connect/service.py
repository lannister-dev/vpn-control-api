from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.backend_peers.repository import BackendPeerRepository
from services.config import get_settings
from services.connect.schemas import ConnectIn, ConnectOut
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import NodeRole
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.routing.service import RoutingService
from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.keys.schemas import VpnKeyInternalCreate, VpnProtocol, VpnTransport
from shared.database.session import AsyncDatabase
from shared.profiles.builder import VlessUriBuilder
from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.registry import ProfileRegistry
from shared.profiles.schemas import NodePublic, RealityTcpProfile, WsTlsProfile
from shared.profiles.types import ProfileType


class ConnectService:
    def __init__(self, session: AsyncSession):
        self.settings = get_settings()
        self.user_repository = UserRepository(session)
        self.key_repository = VpnKeyRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.backend_peer_repository = BackendPeerRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.routing_service = RoutingService(session)

    async def connect(self, payload: ConnectIn) -> ConnectOut:
        user = await self.user_repository.get_by_id(payload.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        profile = self._resolve_profile(payload.profile_key)
        transport = self._infer_transport(profile.type)

        key = await self._resolve_key(payload=payload, transport=transport)
        existing_placement = await self.placement_repository.get_by_key_id(key.id)
        if existing_placement and existing_placement.desired_state == PlacementDesiredState.active.value:
            existing_route = await self._resolve_existing_route(
                existing_placement=existing_placement,
                preferred_region=payload.preferred_region,
            )
            if existing_route is not None:
                backend_node, gateway_node = existing_route
                await self._ensure_backend_peers_for_all_gateways(
                    backend_node=backend_node,
                    selected_gateway=gateway_node,
                    preferred_region=payload.preferred_region,
                )
                return self._build_connect_out(
                    key=key,
                    placement=existing_placement,
                    backend_node=backend_node,
                    gateway_node=gateway_node,
                    profile=profile,
                )

        backend_node = await self._select_backend(preferred_region=payload.preferred_region)
        gateway_node = await self._select_gateway(
            gateway_node_id=payload.gateway_node_id,
            preferred_region=payload.preferred_region,
            fallback=backend_node,
        )
        await self._ensure_backend_peers_for_all_gateways(
            backend_node=backend_node,
            selected_gateway=gateway_node,
            preferred_region=payload.preferred_region,
        )

        migration_reason = "connect_initial" if existing_placement is None else "connect_rebalance"
        placement = await self.placement_repository.upsert_set_pending(
            key_id=key.id,
            backend_node_id=backend_node.id,
            gateway_node_id=None,
            desired_state=PlacementDesiredState.active.value,
            sticky_until=None,
            last_migration_reason=migration_reason,
        )
        if not placement:
            raise HTTPException(status_code=500, detail="Failed to create placement")
        return self._build_connect_out(
            key=key,
            placement=placement,
            backend_node=backend_node,
            gateway_node=gateway_node,
            profile=profile,
        )

    def _resolve_profile(self, profile_key: str) -> WsTlsProfile | RealityTcpProfile:
        try:
            return ProfileRegistry.get(profile_key).profile
        except ProfileRegistryError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def _infer_transport(self, profile_type: ProfileType) -> VpnTransport:
        if profile_type == ProfileType.ws_tls:
            return VpnTransport.ws
        if profile_type == ProfileType.reality_tcp:
            return VpnTransport.tcp
        raise HTTPException(status_code=422, detail=f"Unsupported profile type: {profile_type}")

    async def _resolve_key(self, *, payload: ConnectIn, transport: VpnTransport):
        if payload.key_id is not None:
            key = await self.key_repository.get_by_id(payload.key_id)
            if not key:
                raise HTTPException(status_code=404, detail="Key not found")
            if key.user_id != payload.user_id:
                raise HTTPException(status_code=409, detail="Key does not belong to user")
            if key.is_revoked:
                raise HTTPException(status_code=409, detail="Key is revoked")
            if key.transport != transport.value:
                raise HTTPException(
                    status_code=409,
                    detail=f"Key transport '{key.transport}' does not match profile transport '{transport.value}'",
                )
            return key

        key = await self.key_repository.get_latest_active_for_user(
            user_id=payload.user_id,
            transport=transport.value,
        )
        if key:
            return key

        valid_until = payload.valid_until
        if valid_until is None:
            valid_until = datetime.now(timezone.utc) + timedelta(days=365)

        key_internal = VpnKeyInternalCreate(
            user_id=payload.user_id,
            protocol=VpnProtocol.vless,
            transport=transport,
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
        if not candidates:
            raise HTTPException(status_code=503, detail="No eligible backend node available")
        return candidates[0]

    async def _resolve_existing_route(
            self,
            *,
            existing_placement,
            preferred_region: str | None,
    ) -> tuple[VpnNode, VpnNode] | None:
        backend_node = await self.node_repository.get_by_id(existing_placement.backend_node_id)
        if backend_node is None or not self._is_backend_eligible(backend_node):
            return None

        if existing_placement.gateway_node_id is not None:
            gateway_node = await self.node_repository.get_by_id(existing_placement.gateway_node_id)
            if gateway_node is None or not self._is_gateway_eligible(gateway_node, strict_role=True):
                return None
        else:
            gateway_node = await self._select_gateway(
                gateway_node_id=None,
                preferred_region=preferred_region,
                fallback=backend_node,
            )

        return backend_node, gateway_node

    async def _select_gateway(
            self,
            *,
            gateway_node_id: UUID | None,
            preferred_region: str | None,
            fallback: VpnNode,
    ) -> VpnNode:
        if gateway_node_id is not None:
            gateway = await self.node_repository.get_by_id(gateway_node_id)
            if not gateway:
                raise HTTPException(status_code=404, detail="Gateway node not found")
            if not self._is_gateway_eligible(gateway, strict_role=True):
                raise HTTPException(status_code=409, detail="Gateway node is not eligible")
            return gateway

        if self._is_gateway_eligible(fallback, strict_role=True):
            return fallback

        public_nodes = await self.node_repository.list_public(
            preferred_region=preferred_region,
            role=NodeRole.gateway.value,
        )
        for node in public_nodes:
            if self._is_gateway_eligible(node, strict_role=True):
                return node

        # Transitional fallback for single-node/legacy setups before roles are configured.
        if self._is_gateway_eligible(fallback, strict_role=False):
            return fallback

        raise HTTPException(status_code=503, detail="No eligible gateway node available")

    async def _ensure_backend_peers_for_all_gateways(
            self,
            *,
            backend_node: VpnNode,
            selected_gateway: VpnNode,
            preferred_region: str | None,
    ) -> None:
        gateways_by_id: dict[UUID, VpnNode] = {}
        gateways_by_id[selected_gateway.id] = selected_gateway

        regional_gateways = await self.node_repository.list_public(
            preferred_region=preferred_region,
            role=NodeRole.gateway.value,
        )
        if not isinstance(regional_gateways, list):
            regional_gateways = []

        if not regional_gateways and preferred_region:
            regional_gateways = await self.node_repository.list_public(
                role=NodeRole.gateway.value,
            )
            if not isinstance(regional_gateways, list):
                regional_gateways = []

        for gateway in regional_gateways:
            if self._is_gateway_eligible(gateway, strict_role=True):
                gateways_by_id[gateway.id] = gateway

        for gateway in gateways_by_id.values():
            await self.backend_peer_repository.ensure_active_pair(
                backend_node_id=backend_node.id,
                gateway_node_id=gateway.id,
            )

    def _is_backend_eligible(self, node: VpnNode) -> bool:
        if not getattr(node, "is_active", True):
            return False
        if not getattr(node, "is_enabled", True):
            return False
        if getattr(node, "is_draining", False):
            return False
        role = getattr(node, "role", None)
        if not isinstance(role, str):
            role = None
        if role != NodeRole.backend.value:
            return False
        return bool((getattr(node, "internal_wg_ip", "") or "").strip())

    def _is_gateway_eligible(self, node: VpnNode, *, strict_role: bool) -> bool:
        if not getattr(node, "is_active", True):
            return False
        if not getattr(node, "is_enabled", True):
            return False
        if getattr(node, "is_draining", False):
            return False
        role = getattr(node, "role", None)
        if not isinstance(role, str):
            role = None
        if strict_role and role != NodeRole.gateway.value:
            return False
        return bool((getattr(node, "public_domain", "") or "").strip())

    def _build_connect_out(
            self,
            *,
            key,
            placement,
            backend_node: VpnNode,
            gateway_node: VpnNode,
            profile: WsTlsProfile | RealityTcpProfile,
    ) -> ConnectOut:
        public_domain = self.settings.edge.public_domain or gateway_node.public_domain
        node_public = NodePublic(
            domain=public_domain,
            port=443,
            remark=gateway_node.name,
            region=gateway_node.region,
        )
        uri = VlessUriBuilder.build(
            client_id=key.client_id,
            node=node_public,
            profile=profile,
        )
        return ConnectOut(
            key_id=key.id,
            client_id=key.client_id,
            gateway_node_id=gateway_node.id,
            backend_node_id=backend_node.id,
            placement_id=placement.id,
            placement_op_version=placement.op_version,
            uri=uri,
        )


def get_connect_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> ConnectService:
    return ConnectService(session)
