from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.backend_peers.repository import BackendPeerRepository
from services.config import get_settings
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import NodeRole
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.routing.service import RoutingService
from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.keys.schemas import (
    VpnKeyInternalCreate,
    VpnProtocol,
    VpnTransport,
)
from services.vpn.subscriptions.constants import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SEC
from services.vpn.subscriptions.exceptions import (
    SubscriptionBuild,
    SubscriptionDeviceLimitReached,
    SubscriptionExpired,
    SubscriptionHwidRequired,
    SubscriptionInactive,
    SubscriptionNotFound,
    SubscriptionRateLimited,
    SubscriptionTokenExpired,
)
from services.vpn.subscriptions.model import Subscription
from services.vpn.subscriptions.repository import SubscriptionDeviceRepository, SubscriptionRepository
from services.vpn.subscriptions.schemas import (
    SubscriptionCreateIn,
    SubscriptionCreatedOut,
    SubscriptionDeviceCreate,
    SubscriptionDeviceOut,
    SubscriptionInternalCreate,
    SubscriptionInternalRotate,
    SubscriptionInternalUpdate,
    SubscriptionRotateOut,
)
from services.vpn.subscriptions.utils import SubscriptionUtils
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import SUBSCRIPTION_BUILD_DURATION
from shared.profiles.builder import VlessUriBuilder
from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.registry import ProfileRegistry
from shared.profiles.schemas import NodePublic, RealityTcpProfile, WsTlsProfile
from shared.profiles.types import ProfileType
from shared.redis.client import RedisClient, get_redis_client


class SubscriptionService:
    def __init__(self, session: AsyncSession, redis: RedisClient):
        self.settings = get_settings()
        self.session = session
        self.redis = redis
        self.subscription_repository = SubscriptionRepository(session)
        self.device_repository = SubscriptionDeviceRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.routing_service = RoutingService(session)
        self.backend_peer_repository = BackendPeerRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.user_repository = UserRepository(session)
        self.vpn_key_repository = VpnKeyRepository(session)

    async def create(self, data: SubscriptionCreateIn) -> SubscriptionCreatedOut:
        user = await self.user_repository.get_by_id(data.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not data.profile_key:
            raise HTTPException(
                status_code=422,
                detail="profile_key is required to create a subscription",
            )

        raw_token = SubscriptionUtils.generate()
        token_hash = SubscriptionUtils.hash(raw_token)

        # Legacy client_id in subscription is used only when HWID mode is disabled.
        client_uuid = uuid4()

        bound_key = None
        if data.vpn_key_id is not None:
            bound_key = await self.vpn_key_repository.get_by_id(data.vpn_key_id)
            if not bound_key:
                raise HTTPException(status_code=404, detail="Key not found")
            if bound_key.user_id != data.user_id:
                raise HTTPException(status_code=409, detail="Key does not belong to user")
            if bound_key.is_revoked:
                raise HTTPException(status_code=409, detail="Key is revoked")
            try:
                client_uuid = UUID(bound_key.client_id)
            except Exception as exc:
                raise HTTPException(status_code=409, detail="Key client_id is not a UUID") from exc

        try:
            profile = ProfileRegistry.get(data.profile_key).profile
        except ProfileRegistryError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        transport = self._infer_transport(profile.type)

        if bound_key is not None and bound_key.transport != transport.value:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Key transport '{bound_key.transport}' does not match profile transport '{transport.value}'"
                ),
            )

        valid_until = data.expires_at
        if valid_until is None:
            valid_until = datetime.now(timezone.utc) + timedelta(days=365)

        settings = get_settings()
        hwid_enabled = data.hwid_enabled
        if hwid_enabled is None:
            hwid_enabled = settings.subscriptions.require_hwid_default

        if hwid_enabled and bound_key is not None:
            raise HTTPException(
                status_code=409,
                detail="vpn_key_id binding is not supported for HWID subscriptions",
            )

        internal = SubscriptionInternalCreate(
            user_id=data.user_id,
            client_id=client_uuid,
            root_vpn_key_id=bound_key.id if bound_key else None,
            token_hash=token_hash,
            is_active=True,
            expires_at=data.expires_at,
            profile_key=data.profile_key,
            preferred_region=data.preferred_region,
            hwid_enabled=bool(hwid_enabled),
            max_devices=data.max_devices,
        )
        subscription = await self.subscription_repository.create(internal.model_dump())

        vpn_key_id: UUID | None = None

        # Legacy mode: one key per subscription.
        if not subscription.hwid_enabled and bound_key is None:
            key_internal = VpnKeyInternalCreate(
                user_id=data.user_id,
                protocol=VpnProtocol.vless,
                transport=transport,
                client_id=str(client_uuid),
                valid_until=valid_until,
                traffic_limit_mb=1000,
                is_revoked=False,
            )
            vpn_key = await self.vpn_key_repository.create(key_internal.model_dump())
            vpn_key_id = vpn_key.id
        elif bound_key is not None:
            vpn_key_id = bound_key.id

        return SubscriptionCreatedOut(
            id=subscription.id,
            client_id=subscription.client_id,
            vpn_key_id=vpn_key_id,
            token=raw_token,
            expires_at=subscription.expires_at,
            is_active=subscription.is_active,
        )

    async def rotate_token(
            self,
            subscription_id: UUID,
            *,
            grace_seconds: int = 3600,
    ) -> SubscriptionRotateOut:
        sub = await self.subscription_repository.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound

        new_raw = SubscriptionUtils.generate()
        new_hash = SubscriptionUtils.hash(new_raw)
        now = datetime.now(timezone.utc)

        data = SubscriptionInternalRotate(
            token_hash=new_hash,
            prev_token_hash=sub.token_hash,
            prev_token_expires_at=now + timedelta(seconds=grace_seconds),
            updated_at=now,
        )

        updated = await self.subscription_repository.update_by_id(
            subscription_id,
            data.model_dump(),
        )
        if not updated:
            raise SubscriptionNotFound

        await self._invalidate_rate_limit(sub.token_hash)
        await self._invalidate_rate_limit(new_hash)

        return SubscriptionRotateOut(token=new_raw)

    async def deactivate(self, subscription_id: UUID) -> int:
        """
        Hard deactivation:
        - mark subscription inactive
        - revoke all related keys (root + device keys)
        - move existing placements for these keys to desired_state=inactive

        Returns number of keys that were processed.
        """
        subscription = await self.subscription_repository.get_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFound(subscription_id)

        now = datetime.now(timezone.utc)
        await self.subscription_repository.update_by_id(
            item_id=subscription.id,
            data=SubscriptionInternalUpdate(
                is_active=False,
                updated_at=now,
            ).model_dump(),
        )

        key_ids = await self._collect_subscription_key_ids(subscription)

        processed = 0
        for key_id in key_ids:
            key = await self.vpn_key_repository.get_by_id(key_id)
            if not key:
                continue

            key.is_revoked = True
            await self._set_placement_desired_state(
                key_id=key_id,
                desired_state=PlacementDesiredState.inactive,
                reason="subscription_deactivate",
            )
            processed += 1

        return processed

    async def activate(self, subscription_id: UUID) -> int:
        subscription = await self.subscription_repository.get_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFound(subscription_id)

        await self.subscription_repository.update_by_id(
            item_id=subscription.id,
            data=SubscriptionInternalUpdate(
                is_active=True,
                updated_at=datetime.now(timezone.utc),
            ).model_dump(),
        )
        key_ids = await self._collect_subscription_key_ids(subscription)

        restored = 0
        for key_id in key_ids:
            key = await self.vpn_key_repository.get_by_id(key_id)
            if not key:
                continue

            if key.is_revoked:
                key.is_revoked = False
                restored += 1

            await self._set_placement_desired_state(
                key_id=key_id,
                desired_state=PlacementDesiredState.active,
                reason="subscription_activate",
            )
        return restored

    async def bind_root_key(self, subscription_id: UUID, vpn_key_id: UUID) -> None:
        """
        Admin-only helper: bind subscription to an existing key (legacy mode).
        If subscription is HWID-enabled, binding is rejected.
        """
        sub = await self.subscription_repository.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound(subscription_id)
        if getattr(sub, "hwid_enabled", False):
            raise HTTPException(status_code=409, detail="Cannot bind root key for HWID subscription")

        key = await self.vpn_key_repository.get_by_id(vpn_key_id)
        if not key:
            raise HTTPException(status_code=404, detail="Key not found")
        if key.user_id != sub.user_id:
            raise HTTPException(status_code=409, detail="Key does not belong to subscription user")
        if key.is_revoked:
            raise HTTPException(status_code=409, detail="Key is revoked")

        try:
            new_client_uuid = UUID(key.client_id)
        except Exception as exc:
            raise HTTPException(status_code=409, detail="Key client_id is not a UUID") from exc

        await self.subscription_repository.update_by_id(
            sub.id,
            {
                "root_vpn_key_id": key.id,
                "client_id": new_client_uuid,
                "updated_at": datetime.now(timezone.utc),
            },
        )

    async def list_devices(
            self,
            subscription_id: UUID,
            *,
            active_only: bool = False,
    ) -> list[SubscriptionDeviceOut]:
        subscription = await self.subscription_repository.get_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFound(subscription_id)

        devices = await self.device_repository.list_by_subscription(
            subscription_id,
            active_only=active_only,
        )
        return [SubscriptionDeviceOut.model_validate(d) for d in devices]

    async def revoke_device(self, subscription_id: UUID, device_id: UUID) -> bool:
        """
        Deactivate one device slot and revoke its key.

        Returns True if key state changed (not revoked -> revoked),
        False when key was already revoked or missing.
        """
        subscription = await self.subscription_repository.get_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFound(subscription_id)

        device = await self.device_repository.get_by_id_for_subscription(
            subscription_id=subscription_id,
            device_id=device_id,
        )
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        now = datetime.now(timezone.utc)
        if device.is_active:
            await self.device_repository.update_by_id(
                device.id,
                {"is_active": False, "updated_at": now},
            )

        key = await self.vpn_key_repository.get_by_id(device.vpn_key_id)
        if not key:
            return False

        changed = False
        if not key.is_revoked:
            key.is_revoked = True
            changed = True

        await self._set_placement_desired_state(
            key_id=key.id,
            desired_state=PlacementDesiredState.inactive,
            reason="subscription_device_revoke",
        )
        return changed

    async def _collect_subscription_key_ids(self, subscription) -> set[UUID]:
        key_ids: set[UUID] = set(
            await self.device_repository.list_key_ids_for_subscription(subscription.id)
        )
        root_key_id = getattr(subscription, "root_vpn_key_id", None)
        if root_key_id:
            key_ids.add(root_key_id)
        return key_ids

    async def build_payload(
            self,
            raw_token: str,
            *,
            hwid: str | None = None,
            user_agent: str | None = None,
            if_none_match: str | None = None,
    ) -> tuple[str, str, bool]:
        t0 = time.perf_counter()

        token_hash = SubscriptionUtils.hash(raw_token)
        await self._enforce_rate_limit(token_hash)

        subscription = await self.subscription_repository.get_by_any_token_hash(token_hash)
        if not subscription:
            raise SubscriptionNotFound("subscription")

        self._validate_subscription(subscription, token_hash)

        now = datetime.now(timezone.utc)
        client_id, vpn_key_id = await self._resolve_client_for_request(
            subscription=subscription,
            hwid=hwid,
            user_agent=user_agent,
            now=now,
        )

        if vpn_key_id is None:
            raise SubscriptionBuild("No available key")

        _, gateway_node = await self._ensure_route_for_key(
            key_id=vpn_key_id,
            preferred_region=subscription.preferred_region,
        )

        profiles = self._select_profiles(subscription.profile_key)

        uris = self._build_uris(
            client_id=client_id,
            nodes=[gateway_node],
            profiles=profiles,
        )

        if not uris:
            raise SubscriptionBuild("No available configs")

        payload = "\n".join(uris)
        etag = self._calc_etag(subscription, [gateway_node], profiles, client_id=client_id)

        SUBSCRIPTION_BUILD_DURATION.observe(time.perf_counter() - t0)

        if if_none_match and if_none_match == etag:
            return "", etag, True

        return payload, etag, False

    def _validate_subscription(self, subscription, token_hash: str) -> None:
        now = datetime.now(timezone.utc)

        if not subscription.is_active:
            raise SubscriptionInactive()

        if subscription.expires_at and subscription.expires_at <= now:
            raise SubscriptionExpired()

        if subscription.prev_token_hash == token_hash:
            if subscription.prev_token_expires_at and subscription.prev_token_expires_at <= now:
                raise SubscriptionTokenExpired()

    def _select_profiles(
            self,
            profile_key: str | None,
    ) -> list[WsTlsProfile | RealityTcpProfile]:
        try:
            if profile_key:
                return [ProfileRegistry.get(profile_key).profile]
            return [
                ProfileRegistry.get(k).profile
                for k in ProfileRegistry.all_keys()
            ]
        except ProfileRegistryError as exc:
            raise SubscriptionBuild(str(exc)) from exc

    def _build_uris(
            self,
            *,
            client_id: str,
            nodes: Iterable,
            profiles: Iterable[WsTlsProfile | RealityTcpProfile],
    ) -> list[str]:
        result: list[str] = []

        for node in nodes:
            domain = self._resolve_public_domain(node)
            node_public = NodePublic(
                domain=domain,
                port=443,
                remark=node.name,
                region=node.region,
            )
            for profile in profiles:
                try:
                    result.append(
                        VlessUriBuilder.build(
                            client_id=client_id,
                            node=node_public,
                            profile=profile,
                        )
                    )
                except Exception:
                    continue

        return result

    def _calc_etag(self, sub, nodes, profiles, *, client_id: str) -> str:
        profile_parts: list[str] = []
        for profile in profiles:
            model_dump_json = getattr(profile, "model_dump_json", None)
            dumped = None
            payload: str

            if callable(model_dump_json):
                dumped = model_dump_json()
                if isinstance(dumped, bytes):
                    payload = dumped.decode()
                elif isinstance(dumped, str):
                    payload = dumped
                else:
                    dumped = None

            if dumped is None:
                payload = f"{getattr(profile, 'type', 'unknown')}:{getattr(profile, 'version', '')}"

            profile_parts.append(hashlib.sha256(payload.encode()).hexdigest())

        base = "|".join([
            str(sub.id),
            sub.updated_at.isoformat(),
            sub.profile_key or "",
            sub.preferred_region or "",
            client_id,
            ",".join(sorted(self._resolve_public_domain(n) for n in nodes)),
            ",".join(sorted(profile_parts)),
        ])
        return hashlib.sha256(base.encode()).hexdigest()

    def _infer_transport(self, profile_type: ProfileType) -> VpnTransport:
        if profile_type == ProfileType.ws_tls:
            return VpnTransport.ws
        if profile_type == ProfileType.reality_tcp:
            return VpnTransport.tcp
        raise HTTPException(status_code=422, detail=f"Unsupported profile type: {profile_type}")

    async def _ensure_route_for_key(
            self,
            *,
            key_id: UUID,
            preferred_region: str | None,
    ) -> tuple[VpnNode, VpnNode]:
        placement = await self.placement_repository.get_by_key_id(key_id)
        if placement and placement.desired_state == PlacementDesiredState.active.value:
            existing = await self._resolve_existing_route(
                placement=placement,
                preferred_region=preferred_region,
            )
            if existing is not None:
                backend_node, gateway_node = existing
                await self._ensure_backend_peers_for_all_gateways(
                    backend_node=backend_node,
                    selected_gateway=gateway_node,
                    preferred_region=preferred_region,
                )
                return backend_node, gateway_node

        backend_node = await self._select_backend(preferred_region=preferred_region)
        gateway_node = await self._select_gateway(
            gateway_node_id=None,
            preferred_region=preferred_region,
            fallback=backend_node,
        )
        await self._ensure_backend_peers_for_all_gateways(
            backend_node=backend_node,
            selected_gateway=gateway_node,
            preferred_region=preferred_region,
        )

        migration_reason = "subscription_initial" if placement is None else "subscription_rebalance"
        new_placement = await self.placement_repository.upsert_set_pending(
            key_id=key_id,
            backend_node_id=backend_node.id,
            gateway_node_id=None,
            desired_state=PlacementDesiredState.active.value,
            sticky_until=None,
            last_migration_reason=migration_reason,
        )
        if not new_placement:
            raise SubscriptionBuild("Failed to create placement")
        return backend_node, gateway_node

    async def _resolve_existing_route(
            self,
            *,
            placement,
            preferred_region: str | None,
    ) -> tuple[VpnNode, VpnNode] | None:
        backend_node = await self.node_repository.get_by_id(placement.backend_node_id)
        if backend_node is None or not self._is_backend_eligible(backend_node):
            return None

        if placement.gateway_node_id is not None:
            gateway_node = await self.node_repository.get_by_id(placement.gateway_node_id)
            if gateway_node is None or not self._is_gateway_eligible(gateway_node, strict_role=True):
                return None
        else:
            gateway_node = await self._select_gateway(
                gateway_node_id=None,
                preferred_region=preferred_region,
                fallback=backend_node,
            )

        return backend_node, gateway_node

    async def _select_backend(self, *, preferred_region: str | None) -> VpnNode:
        candidates = await self.routing_service.select_nodes(
            preferred_region=preferred_region,
            role=NodeRole.backend.value,
        )
        if not candidates:
            raise SubscriptionBuild("No available backend nodes")
        return candidates[0]

    async def _select_gateway(
            self,
            *,
            gateway_node_id: UUID | None,
            preferred_region: str | None,
            fallback: VpnNode,
    ) -> VpnNode:
        if gateway_node_id is not None:
            gateway = await self.node_repository.get_by_id(gateway_node_id)
            if gateway is None:
                raise SubscriptionBuild("No available gateway nodes")
            if not self._is_gateway_eligible(gateway, strict_role=True):
                raise SubscriptionBuild("No available gateway nodes")
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

        raise SubscriptionBuild("No available gateway nodes")

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
        if strict_role and role != NodeRole.gateway.value:
            return False
        return bool((getattr(node, "public_domain", "") or "").strip())

    def _resolve_public_domain(self, node: VpnNode) -> str:
        domain = self.settings.edge.public_domain
        if domain:
            return domain
        return (getattr(node, "public_domain", "") or "").strip()

    async def _set_placement_desired_state(
            self,
            *,
            key_id: UUID,
            desired_state: PlacementDesiredState,
            reason: str,
    ) -> None:
        placement = await self.placement_repository.get_by_key_id(key_id)
        if placement is None:
            return

        await self.placement_repository.upsert_set_pending(
            key_id=key_id,
            backend_node_id=placement.backend_node_id,
            gateway_node_id=placement.gateway_node_id,
            desired_state=desired_state.value,
            sticky_until=placement.sticky_until,
            last_migration_reason=reason,
        )

    def _hash_hwid(self, hwid: str) -> str:
        normalized = hwid.strip()
        if not normalized:
            raise SubscriptionHwidRequired()
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def _resolve_client_for_request(
            self,
            *,
            subscription,
            hwid: str | None,
            user_agent: str | None,
            now: datetime,
    ) -> tuple[str, UUID | None]:
        """
        Returns (client_id, vpn_key_id).

        If HWID is enabled (per-sub or default), client_id is bound to the device-specific VpnKey.
        Otherwise, subscription is bound to a single key (root key or legacy key by client_id).
        """
        settings = get_settings()
        hwid_required = bool(subscription.hwid_enabled or settings.subscriptions.require_hwid_default)

        if not hwid and hwid_required:
            raise SubscriptionHwidRequired()

        if not hwid:
            # Prefer explicit binding when present.
            if getattr(subscription, "root_vpn_key_id", None):
                key = await self.vpn_key_repository.get_by_id(subscription.root_vpn_key_id)
                if not key:
                    raise SubscriptionBuild("Root key not found")
                if getattr(key, "is_revoked", False):
                    raise SubscriptionBuild("Root key is revoked")
                return key.client_id, key.id

            client_id = str(subscription.client_id)
            key = await self.vpn_key_repository.get_one_by(client_id=client_id, is_active=True)
            if key and not getattr(key, "is_revoked", False):
                return client_id, key.id

            # Hardening: if there is no key matching subscription.client_id, create one on-demand.
            if not subscription.profile_key:
                raise SubscriptionBuild("profile_key is required")
            try:
                profile = ProfileRegistry.get(subscription.profile_key).profile
            except ProfileRegistryError as exc:
                raise SubscriptionBuild(str(exc)) from exc

            transport = self._infer_transport(profile.type)
            valid_until = subscription.expires_at
            if valid_until is None:
                valid_until = now + timedelta(days=365)

            key_internal = VpnKeyInternalCreate(
                user_id=subscription.user_id,
                protocol=VpnProtocol.vless,
                transport=transport,
                client_id=client_id,
                valid_until=valid_until,
                traffic_limit_mb=1000,
                is_revoked=False,
            )
            created = await self.vpn_key_repository.create(key_internal.model_dump())
            return client_id, created.id

        hwid_hash = self._hash_hwid(hwid)
        device = await self.device_repository.get_active_by_sub_and_hwid_hash(
            subscription_id=subscription.id,
            hwid_hash=hwid_hash,
        )
        if device:
            await self.device_repository.touch(
                device_id=device.id,
                last_seen_at=now,
                user_agent=user_agent,
            )
            key = await self.vpn_key_repository.get_by_id(device.vpn_key_id)
            if not key:
                raise SubscriptionBuild("Device key not found")
            return key.client_id, key.id

        await self._lock_subscription_for_device_allocation(subscription.id)
        # Re-check after lock: another request may have already provisioned this HWID.
        device = await self.device_repository.get_active_by_sub_and_hwid_hash(
            subscription_id=subscription.id,
            hwid_hash=hwid_hash,
        )
        if device:
            await self.device_repository.touch(
                device_id=device.id,
                last_seen_at=now,
                user_agent=user_agent,
            )
            key = await self.vpn_key_repository.get_by_id(device.vpn_key_id)
            if not key:
                raise SubscriptionBuild("Device key not found")
            return key.client_id, key.id

        max_devices = subscription.max_devices or settings.subscriptions.max_devices_default
        current = await self.device_repository.count_active_for_subscription(subscription.id)
        if current >= max_devices:
            raise SubscriptionDeviceLimitReached()

        if not subscription.profile_key:
            raise SubscriptionBuild("profile_key is required")
        try:
            profile = ProfileRegistry.get(subscription.profile_key).profile
        except ProfileRegistryError as exc:
            raise SubscriptionBuild(str(exc)) from exc

        transport = self._infer_transport(profile.type)
        valid_until = subscription.expires_at
        if valid_until is None:
            valid_until = now + timedelta(days=365)

        key_internal = VpnKeyInternalCreate(
            user_id=subscription.user_id,
            protocol=VpnProtocol.vless,
            transport=transport,
            client_id=str(uuid4()),
            valid_until=valid_until,
            traffic_limit_mb=1000,
            is_revoked=False,
        )
        vpn_key = await self.vpn_key_repository.create(key_internal.model_dump())

        try:
            await self.device_repository.create(
                SubscriptionDeviceCreate(
                    subscription_id=subscription.id,
                    hwid_hash=hwid_hash,
                    vpn_key_id=vpn_key.id,
                    last_seen_at=now,
                    user_agent=user_agent,
                ).model_dump()
            )
        except IntegrityError:
            # Race: device mapping was created by another concurrent request.
            device = await self.device_repository.get_active_by_sub_and_hwid_hash(
                subscription_id=subscription.id,
                hwid_hash=hwid_hash,
            )
            if not device:
                raise
            key = await self.vpn_key_repository.get_by_id(device.vpn_key_id)
            if not key:
                raise SubscriptionBuild("Device key not found")
            return key.client_id, key.id

        return vpn_key.client_id, vpn_key.id

    async def _lock_subscription_for_device_allocation(self, subscription_id: UUID) -> None:
        await self.session.execute(
            select(Subscription.id)
            .where(Subscription.id == subscription_id)
            .with_for_update()
        )

    def _rl_key(self, token_hash: str) -> str:
        return f"sub:rl:{token_hash}"

    async def _enforce_rate_limit(self, token_hash: str) -> None:
        key = self._rl_key(token_hash)
        current = int(await self.redis.client.incr(key))
        if current == 1:
            await self.redis.client.expire(key, RATE_LIMIT_WINDOW_SEC)
        if current > RATE_LIMIT_REQUESTS:
            raise SubscriptionRateLimited()

    async def _invalidate_rate_limit(self, token_hash: str) -> None:
        await self.redis.client.delete(self._rl_key(token_hash))


def get_subscription_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> SubscriptionService:
    return SubscriptionService(session, redis)
