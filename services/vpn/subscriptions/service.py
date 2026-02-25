from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
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
from services.vpn.keys.schemas import (
    VpnKeyInternalCreate,
    VpnProtocol,
    VpnTransport,
)
from services.vpn.subscriptions.constants import (
    PAYLOAD_BUILD_LOCK_TTL_SEC,
    PAYLOAD_BUILD_WAIT_ATTEMPTS,
    PAYLOAD_BUILD_WAIT_DELAY_SEC,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SEC,
)
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
    SubscriptionDeviceInternalUpdate,
    SubscriptionDeviceOut,
    SubscriptionInternalCreate,
    SubscriptionInternalRotate,
    SubscriptionInternalUpdate,
    ResolvedSubscriptionRoute,
    SubscriptionRotateOut,
)
from services.vpn.subscriptions.utils import SubscriptionUtils
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import (
    SUBSCRIPTION_BUILD_DURATION,
    SUBSCRIPTION_CACHE_TOTAL,
    SUBSCRIPTION_PAYLOAD_GUARDRAIL_TOTAL,
    SUBSCRIPTION_PAYLOAD_SIZE_BYTES,
)
from shared.profiles.builder import VlessUriBuilder
from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.registry import ProfileRegistry
from shared.profiles.schemas import (
    NodePublic,
    ProfileMetadata,
    RealityTcpClientConfig,
    RealityTcpProfile,
    WsTlsClientConfig,
    WsTlsProfile,
)
from shared.profiles.transport import VlessUri
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
        self.placement_repository = UserPlacementRepository(session)
        self.route_repository = RouteRepository(session)
        self.user_repository = UserRepository(session)
        self.vpn_key_repository = VpnKeyRepository(session)
        self.route_selector = RouteSelector[ResolvedSubscriptionRoute](
            get_backend_id=lambda item: item.backend_node_id,
            get_transport_key=lambda item: (item.transport_security, item.transport_network),
            get_route_id=lambda item: item.route_id,
        )

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

        hwid_enabled = data.hwid_enabled
        if hwid_enabled is None:
            hwid_enabled = self.settings.subscriptions.require_hwid_default

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

        base_subscription_url = f"{self.settings.subscriptions.public_base_url}{raw_token}"

        return SubscriptionCreatedOut(
            id=subscription.id,
            client_id=subscription.client_id,
            vpn_key_id=vpn_key_id,
            token=raw_token,
            subscription_url=base_subscription_url,
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
            data.model_dump(exclude_none=True),
        )
        if not updated:
            raise SubscriptionNotFound

        await self._invalidate_rate_limit(sub.token_hash)
        await self._invalidate_rate_limit(new_hash)
        await self._invalidate_payload_cache_by_token_hash(sub.token_hash)
        await self._invalidate_payload_cache_by_token_hash(new_hash)

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
            ).model_dump(exclude_none=True),
        )
        await self._invalidate_payload_cache_by_token_hash(subscription.token_hash)

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
            ).model_dump(exclude_none=True),
        )
        await self._invalidate_payload_cache_by_token_hash(subscription.token_hash)
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
        if sub.hwid_enabled:
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
            SubscriptionInternalUpdate(
                root_vpn_key_id=key.id,
                client_id=new_client_uuid,
                updated_at=datetime.now(timezone.utc),
            ).model_dump(exclude_none=True),
        )
        await self._invalidate_payload_cache_by_token_hash(sub.token_hash)

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
                SubscriptionDeviceInternalUpdate(
                    is_active=False,
                    updated_at=now,
                ).model_dump(exclude_none=True),
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
        await self._invalidate_payload_cache_by_token_hash(subscription.token_hash)
        return changed

    async def _collect_subscription_key_ids(self, subscription) -> set[UUID]:
        key_ids: set[UUID] = set(
            await self.device_repository.list_key_ids_for_subscription(subscription.id)
        )
        root_key_id = subscription.root_vpn_key_id
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
        cache_ttl = max(0, int(self.settings.subscriptions.response_cache_ttl_sec))
        cache_key = self._sub_payload_cache_key(token_hash=token_hash, hwid=hwid)
        lock_key = self._sub_payload_build_lock_key(token_hash=token_hash, hwid=hwid)
        lock_acquired = False
        if cache_ttl > 0:
            cached_payload, cached_etag, cache_result = await self._read_payload_cache(cache_key)
            SUBSCRIPTION_CACHE_TOTAL.labels(result=cache_result).inc()
            if cached_etag:
                if if_none_match and if_none_match == cached_etag:
                    return "", cached_etag, True
                if cached_payload is not None:
                    return cached_payload, cached_etag, False
            lock_acquired = await self._acquire_payload_build_lock(lock_key)
            SUBSCRIPTION_CACHE_TOTAL.labels(
                result="lock_acquired" if lock_acquired else "lock_contended"
            ).inc()
            if not lock_acquired:
                waited_payload, waited_etag, waited_result = await self._wait_for_cached_payload(cache_key)
                SUBSCRIPTION_CACHE_TOTAL.labels(result=waited_result).inc()
                if waited_etag:
                    if if_none_match and if_none_match == waited_etag:
                        return "", waited_etag, True
                    if waited_payload is not None:
                        return waited_payload, waited_etag, False

        try:
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

            selected_backend_id, placement = await self._ensure_backend_placement_for_key(
                key_id=vpn_key_id,
                preferred_region=subscription.preferred_region,
            )
            route_rows = await self.route_repository.list_resolved_active(
                preferred_node_id=selected_backend_id,
                preferred_region=subscription.preferred_region,
                limit=12,
            )

            resolved_routes: list[ResolvedSubscriptionRoute] = []
            seen_uris: set[str] = set()
            for route, node, transport_profile in route_rows:
                uri = self._build_route_uri(
                    client_id=client_id,
                    node=node,
                    transport_profile=transport_profile,
                )
                if uri is None or uri in seen_uris:
                    continue
                seen_uris.add(uri)
                transport_security = transport_profile.security
                if not isinstance(transport_security, str):
                    transport_security = ""
                transport_network = transport_profile.network
                if not isinstance(transport_network, str):
                    transport_network = ""
                resolved_routes.append(
                    ResolvedSubscriptionRoute(
                        route_id=self._as_uuid(route.id),
                        backend_node_id=self._as_uuid(node.id),
                        transport_security=transport_security.strip().lower(),
                        transport_network=transport_network.strip().lower(),
                        uri=uri,
                        route=route,
                        node=node,
                        transport_profile=transport_profile,
                    )
                )

            max_routes = max(1, min(10, int(self.settings.subscriptions.smart_route_max_count)))
            selected_routes = self.route_selector.select(
                routes=resolved_routes,
                preferred_backend_id=selected_backend_id,
                max_routes=max_routes,
            )
            if not selected_routes:
                raise SubscriptionBuild("No available routes")

            max_payload_bytes = max(512, int(self.settings.subscriptions.response_max_payload_bytes))
            selected_routes, guardrail_result = self._fit_routes_to_payload_limit(
                routes=selected_routes,
                max_payload_bytes=max_payload_bytes,
            )
            if guardrail_result == "trimmed":
                SUBSCRIPTION_PAYLOAD_GUARDRAIL_TOTAL.labels(result="trimmed").inc()
            if not selected_routes:
                SUBSCRIPTION_PAYLOAD_GUARDRAIL_TOTAL.labels(result="rejected").inc()
                raise SubscriptionBuild("Subscription payload exceeds size limit")

            uris = [item.uri for item in selected_routes]
            route_signatures = [
                self._route_signature(
                    route=item.route,
                    node=item.node,
                    transport_profile=item.transport_profile,
                )
                for item in selected_routes
            ]
            payload = "\n".join(uris)
            payload_bytes = len(payload.encode())
            if payload_bytes > max_payload_bytes:
                SUBSCRIPTION_PAYLOAD_GUARDRAIL_TOTAL.labels(result="overflow").inc()
                raise SubscriptionBuild("Subscription payload exceeds size limit")
            SUBSCRIPTION_PAYLOAD_SIZE_BYTES.observe(payload_bytes)
            etag = self._calc_etag(
                subscription,
                route_signatures,
                client_id=client_id,
                placement_op_version=placement.op_version,
            )
            if cache_ttl > 0:
                write_ok = await self._write_payload_cache(
                    token_hash=token_hash,
                    cache_key=cache_key,
                    payload=payload,
                    etag=etag,
                    ttl_sec=cache_ttl,
                )
                SUBSCRIPTION_CACHE_TOTAL.labels(
                    result="write_ok" if write_ok else "write_error"
                ).inc()

            SUBSCRIPTION_BUILD_DURATION.observe(time.perf_counter() - t0)

            if if_none_match and if_none_match == etag:
                return "", etag, True

            return payload, etag, False
        finally:
            if lock_acquired:
                await self._release_payload_build_lock(lock_key)

    def _validate_subscription(self, subscription, token_hash: str) -> None:
        now = datetime.now(timezone.utc)

        if not subscription.is_active:
            raise SubscriptionInactive()

        if subscription.expires_at and subscription.expires_at <= now:
            raise SubscriptionExpired()

        if subscription.prev_token_hash == token_hash:
            if subscription.prev_token_expires_at and subscription.prev_token_expires_at <= now:
                raise SubscriptionTokenExpired()

    def _calc_etag(
            self,
            sub,
            route_signatures: Iterable[str],
            *,
            client_id: str,
            placement_op_version: int | None = None,
    ) -> str:
        sub_updated_at = sub.updated_at
        updated_at = sub_updated_at.isoformat() if sub_updated_at else ""
        base = "|".join([
            str(sub.id),
            updated_at,
            sub.profile_key or "",
            sub.preferred_region or "",
            client_id,
            str(placement_op_version or ""),
            ",".join(route_signatures),
        ])
        return hashlib.sha256(base.encode()).hexdigest()

    def _infer_transport(self, profile_type: ProfileType) -> VpnTransport:
        if profile_type == ProfileType.ws_tls:
            return VpnTransport.ws
        if profile_type == ProfileType.reality_tcp:
            return VpnTransport.tcp
        raise HTTPException(status_code=422, detail=f"Unsupported profile type: {profile_type}")

    async def _ensure_backend_placement_for_key(
            self,
            *,
            key_id: UUID,
            preferred_region: str | None,
    ) -> tuple[UUID, UserPlacement]:
        placement = await self.placement_repository.get_by_key_id(key_id)

        selected_backend: VpnNode | None = None
        if placement and placement.desired_state == PlacementDesiredState.active.value:
            backend = await self.node_repository.get_by_id(placement.backend_node_id)
            if backend is not None and self._is_backend_eligible(backend):
                selected_backend = backend

        if selected_backend is None:
            selected_backend = await self._select_backend(preferred_region=preferred_region)
            selected_backend_id = self._as_uuid(str(selected_backend.id))
            migration_reason = "subscription_initial" if placement is None else "subscription_rebalance"
            placement = await self.placement_repository.upsert_set_pending(
                key_id=key_id,
                backend_node_id=selected_backend_id,
                desired_state=PlacementDesiredState.active.value,
                sticky_until=None,
                last_migration_reason=migration_reason,
            )
            if not placement:
                raise SubscriptionBuild("Failed to create placement")
        elif placement is None:
            selected_backend_id = self._as_uuid(str(selected_backend.id))
            placement = await self.placement_repository.upsert_set_pending(
                key_id=key_id,
                backend_node_id=selected_backend_id,
                desired_state=PlacementDesiredState.active.value,
                sticky_until=None,
                last_migration_reason="subscription_initial",
            )
            if not placement:
                raise SubscriptionBuild("Failed to create placement")
        else:
            selected_backend_id = self._as_uuid(str(selected_backend.id))

        if placement is None:
            raise SubscriptionBuild("Failed to create placement")

        return selected_backend_id, placement

    async def _select_backend(self, *, preferred_region: str | None) -> VpnNode:
        candidates = await self.routing_service.select_nodes(
            preferred_region=preferred_region,
            role=NodeRole.backend.value,
        )
        if not candidates:
            raise SubscriptionBuild("No available backend nodes")
        return candidates[0]

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

    def _build_route_uri(
            self,
            *,
            client_id: str,
            node: VpnNode,
            transport_profile,
    ) -> str | None:
        domain = self._resolve_public_domain(node)
        if not domain:
            return None

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
                    remark=node.name,
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
            remark=node.name,
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
                    path="/ws",
                    host=fallback_domain,
                    sni=fallback_domain,
                ),
            )

        return None

    def _route_signature(self, *, route, node, transport_profile) -> str:
        route_updated = route.updated_at
        transport_updated = transport_profile.updated_at
        route_updated_at = route_updated.isoformat() if route_updated else ""
        transport_updated_at = transport_updated.isoformat() if transport_updated else ""
        return "|".join([
            str(route.id),
            str(route.health_status),
            str(route.effective_weight),
            str(node.id),
            self._resolve_public_domain(node),
            str(transport_profile.id),
            str(transport_profile.port),
            route_updated_at,
            transport_updated_at,
        ])

    def _resolve_public_domain(self, node: VpnNode) -> str:
        domain = self.settings.edge.public_domain
        if domain:
            return domain
        return (node.public_domain or "").strip()

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
        hwid_required = bool(
            subscription.hwid_enabled or
            self.settings.subscriptions.require_hwid_default
        )
        if not hwid and hwid_required:
            raise SubscriptionHwidRequired()

        if not hwid:
            # Prefer explicit binding when present.
            if subscription.root_vpn_key_id:
                key = await self.vpn_key_repository.get_by_id(subscription.root_vpn_key_id)
                if not key:
                    raise SubscriptionBuild("Root key not found")
                if key.is_revoked:
                    raise SubscriptionBuild("Root key is revoked")
                return key.client_id, key.id

            client_id = str(subscription.client_id)
            key = await self.vpn_key_repository.get_one_by(client_id=client_id, is_active=True)
            if key and not key.is_revoked:
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

        max_devices = subscription.max_devices or self.settings.subscriptions.max_devices_default
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

    @staticmethod
    def _as_uuid(value: object) -> UUID:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        raise TypeError(f"Expected UUID-compatible value, got {type(value)!r}")

    def _rl_key(self, token_hash: str) -> str:
        return f"sub:rl:{token_hash}"

    def _sub_payload_cache_key(self, *, token_hash: str, hwid: str | None) -> str:
        if hwid is None:
            hwid_marker = "none"
        else:
            normalized = hwid.strip()
            if not normalized:
                hwid_marker = "empty"
            else:
                hwid_marker = hashlib.sha256(normalized.encode()).hexdigest()
        return f"sub:cfg:{token_hash}:{hwid_marker}"

    def _sub_payload_cache_index_key(self, *, token_hash: str) -> str:
        return f"sub:cfg:index:{token_hash}"

    def _sub_payload_build_lock_key(self, *, token_hash: str, hwid: str | None) -> str:
        if hwid is None:
            hwid_marker = "none"
        else:
            normalized = hwid.strip()
            if not normalized:
                hwid_marker = "empty"
            else:
                hwid_marker = hashlib.sha256(normalized.encode()).hexdigest()
        return f"sub:cfg:lock:{token_hash}:{hwid_marker}"

    async def _read_payload_cache(self, cache_key: str) -> tuple[str | None, str | None, str]:
        try:
            raw_value = await self.redis.client.get(cache_key)
        except Exception:
            return None, None, "read_error"
        if not isinstance(raw_value, str) or not raw_value:
            return None, None, "miss"
        try:
            cached = json.loads(raw_value)
        except Exception:
            return None, None, "corrupt"
        if not isinstance(cached, dict):
            return None, None, "corrupt"
        etag = cached.get("etag")
        payload = cached.get("payload")
        if not isinstance(etag, str) or not etag:
            return None, None, "corrupt"
        if payload is not None and not isinstance(payload, str):
            return None, None, "corrupt"
        return payload, etag, "hit"

    async def _write_payload_cache(
            self,
            *,
            token_hash: str,
            cache_key: str,
            payload: str,
            etag: str,
            ttl_sec: int,
    ) -> bool:
        if ttl_sec <= 0:
            return True
        value = json.dumps({"etag": etag, "payload": payload})
        index_key = self._sub_payload_cache_index_key(token_hash=token_hash)
        try:
            await self.redis.client.setex(cache_key, ttl_sec, value)
            await self.redis.client.sadd(index_key, cache_key)
            await self.redis.client.expire(index_key, max(ttl_sec * 4, ttl_sec + 60))
            return True
        except Exception:
            return False

    async def _acquire_payload_build_lock(self, lock_key: str) -> bool:
        try:
            acquired = await self.redis.client.set(
                lock_key,
                "1",
                ex=PAYLOAD_BUILD_LOCK_TTL_SEC,
                nx=True,
            )
            return bool(acquired)
        except Exception:
            return False

    async def _release_payload_build_lock(self, lock_key: str) -> None:
        try:
            await self.redis.client.delete(lock_key)
        except Exception:
            return

    async def _wait_for_cached_payload(self, cache_key: str) -> tuple[str | None, str | None, str]:
        for _ in range(PAYLOAD_BUILD_WAIT_ATTEMPTS):
            await asyncio.sleep(PAYLOAD_BUILD_WAIT_DELAY_SEC)
            payload, etag, result = await self._read_payload_cache(cache_key)
            if result == "hit":
                return payload, etag, "wait_hit"
            if result in {"read_error", "corrupt"}:
                return None, None, f"wait_{result}"
        return None, None, "wait_miss"

    async def _enforce_rate_limit(self, token_hash: str) -> None:
        key = self._rl_key(token_hash)
        current = int(await self.redis.client.incr(key))
        if current == 1:
            await self.redis.client.expire(key, RATE_LIMIT_WINDOW_SEC)
        if current > RATE_LIMIT_REQUESTS:
            raise SubscriptionRateLimited()

    def _fit_routes_to_payload_limit(
            self,
            *,
            routes: list[ResolvedSubscriptionRoute],
            max_payload_bytes: int,
    ) -> tuple[list[ResolvedSubscriptionRoute], str]:
        if max_payload_bytes <= 0:
            return [], "rejected"

        selected: list[ResolvedSubscriptionRoute] = []
        payload_size = 0
        for route in routes:
            route_size = len(route.uri.encode())
            delimiter_size = 1 if selected else 0
            if payload_size + delimiter_size + route_size > max_payload_bytes:
                if not selected:
                    return [], "rejected"
                return selected, "trimmed"
            selected.append(route)
            payload_size += delimiter_size + route_size
        return selected, "ok"

    async def _invalidate_rate_limit(self, token_hash: str) -> None:
        await self.redis.client.delete(self._rl_key(token_hash))

    async def _invalidate_payload_cache_by_token_hash(self, token_hash: str) -> None:
        index_key = self._sub_payload_cache_index_key(token_hash=token_hash)
        try:
            keys = await self.redis.client.smembers(index_key)
            keys_to_delete = [
                key
                for key in keys
                if isinstance(key, str) and key.startswith("sub:cfg:")
            ]
            if keys_to_delete:
                await self.redis.client.delete(*keys_to_delete)
            await self.redis.client.delete(index_key)
        except Exception:
            return


def get_subscription_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> SubscriptionService:
    return SubscriptionService(session, redis)
