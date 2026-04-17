from __future__ import annotations

import asyncio
import hashlib
import json
import time
import urllib.parse
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
    DEFAULT_SUBSCRIPTION_TRANSPORT_BUNDLE,
    PAYLOAD_BUILD_LOCK_TTL_SEC,
    PAYLOAD_BUILD_WAIT_ATTEMPTS,
    PAYLOAD_BUILD_WAIT_DELAY_SEC,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SEC,
    TRANSPORT_PRIORITY,
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
from services.vpn.subscriptions.model import Subscription, SubscriptionDevice
from services.vpn.subscriptions import redis_key
from services.vpn.subscriptions.repository import (
    SubscriptionDeviceKeyRepository,
    SubscriptionDeviceRepository,
    SubscriptionRepository,
)
from services.vpn.subscriptions.schemas import (
    ResolvedDeviceBundle,
    ResolvedDeviceKey,
    SubscriptionCreateIn,
    SubscriptionCreatedOut,
    SubscriptionDeviceCreate,
    SubscriptionDeviceKeyCreate,
    SubscriptionDeviceKeyOut,
    SubscriptionDeviceInternalUpdate,
    SubscriptionDeviceOut,
    SubscriptionInternalCreate,
    SubscriptionInternalRotate,
    SubscriptionInternalUpdate,
    ResolvedSubscriptionRoute,
    SubscriptionOut,
    SubscriptionRotateOut,
    SubscriptionUserInfo,
    TransportBuildResult,
)
from services.vpn.subscriptions.utils import SubscriptionUtils
from shared.database.session import AsyncDatabase
from services.placements.transport import NodeAgentPlacementTransport
from shared.monitoring.metrics import (
    SUBSCRIPTION_BUILD_DURATION,
    SUBSCRIPTION_CACHE_TOTAL,
    SUBSCRIPTION_PAYLOAD_GUARDRAIL_TOTAL,
    SUBSCRIPTION_PAYLOAD_SIZE_BYTES,
)
from shared.profiles.builder import VlessUriBuilder
from shared.profiles.constants import WS_TLS_DEFAULT_PATH
from services.nodes.constants import ROLE_ENTRY, ROLE_WHITELIST_ENTRY
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
from shared.utils.node_display import (
    COUNTRY_CODE_TO_NAME,
    country_code_from_region,
    format_node_display_name,
)
from shared.utils.logger import StructuredLogger

import logging

logger_sub = StructuredLogger(logging.getLogger("subscription-build"))


class SubscriptionService:
    def __init__(self, session: AsyncSession, redis: RedisClient):
        self.settings = get_settings()
        self.session = session
        self.redis = redis
        self.subscription_repository = SubscriptionRepository(session)
        self.device_repository = SubscriptionDeviceRepository(session)
        self.device_key_repository = SubscriptionDeviceKeyRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.routing_service = RoutingService(session)
        self.placement_repository = UserPlacementRepository(session)
        self.node_agent_transport = NodeAgentPlacementTransport(session)
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

        raw_token = SubscriptionUtils.generate()
        token_hash = SubscriptionUtils.hash(raw_token)

        client_uuid = uuid4()

        if data.profile_key:
            try:
                ProfileRegistry.get(data.profile_key)
            except ProfileRegistryError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=self._describe_profile_registry_error(exc),
                ) from exc

        if data.plan_id:
            from services.plans.repository import PlanRepository
            plan_repo = PlanRepository(self.session)
            plan = await plan_repo.get_by_id(data.plan_id)
            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")
            if not plan.is_active:
                raise HTTPException(status_code=422, detail="Plan is not active")

        internal = SubscriptionInternalCreate(
            user_id=data.user_id,
            plan_id=data.plan_id,
            token=raw_token,
            token_hash=token_hash,
            is_active=True,
            expires_at=data.expires_at,
            profile_key=data.profile_key,
            preferred_region=data.preferred_region,
            hwid_enabled=True,
            max_devices=data.max_devices,
        )
        subscription = await self.subscription_repository.create(internal.model_dump())

        subscription_url = f"{self.settings.subscriptions.public_base_url}{raw_token}"

        return SubscriptionCreatedOut(
            id=subscription.id,
            vpn_key_id=None,
            token=raw_token,
            subscription_url=subscription_url,
            expires_at=subscription.expires_at,
            is_active=subscription.is_active,
        )

    async def get_subscription(self, subscription_id: UUID) -> SubscriptionOut:
        sub = await self.subscription_repository.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound(subscription_id)
        return self._sub_to_out(sub)

    @staticmethod
    def _sub_to_out(sub) -> SubscriptionOut:
        plan = getattr(sub, "plan", None)
        return SubscriptionOut(
            id=sub.id,
            user_id=sub.user_id,
            plan_id=sub.plan_id,
            plan_name=plan.name if plan else None,
            token=getattr(sub, "token", None),
            is_active=sub.is_active,
            expires_at=sub.expires_at,
            profile_key=sub.profile_key,
            preferred_region=sub.preferred_region,
            hwid_enabled=sub.hwid_enabled,
            max_devices=sub.max_devices,
            paid_device_slots=getattr(sub, "paid_device_slots", 0),
            used_traffic_bytes=getattr(sub, "used_traffic_bytes", 0),
            lifetime_used_traffic_bytes=getattr(sub, "lifetime_used_traffic_bytes", 0),
            last_traffic_reset_at=getattr(sub, "last_traffic_reset_at", None),
            created_at=sub.created_at,
            updated_at=sub.updated_at,
        )

    async def set_max_devices(
            self,
            subscription_id: UUID,
            max_devices: int,
    ) -> SubscriptionOut:
        sub = await self.subscription_repository.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound(subscription_id)
        update_data = SubscriptionInternalUpdate(max_devices=max_devices)
        updated = await self.subscription_repository.update_by_id(
            subscription_id, update_data.model_dump(exclude_unset=True),
        )
        return self._sub_to_out(updated)

    async def list_subscriptions_by_user(
            self,
            *,
            user_id: UUID,
            active_only: bool = False,
    ) -> list[SubscriptionOut]:
        rows = await self.subscription_repository.list_by_user_id(
            user_id=user_id,
            active_only=active_only,
        )
        return [self._sub_to_out(row) for row in rows]

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
            token=new_raw,
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

        await self.redis.client.delete(redis_key.rate_limit(sub.token_hash))
        await self.redis.client.delete(redis_key.rate_limit(new_hash))
        await self._invalidate_payload_cache_by_token_hash(sub.token_hash)
        await self._invalidate_payload_cache_by_token_hash(new_hash)

        subscription_url = f"{self.settings.subscriptions.public_base_url}{new_raw}"
        return SubscriptionRotateOut(token=new_raw, subscription_url=subscription_url)

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

        key_ids: set[UUID] = set(
            await self.device_repository.list_key_ids_for_subscription(subscription.id)
        )
        key_by_id = await self._load_vpn_keys_by_ids(key_ids)
        processed = 0
        for key_id in key_ids:
            key = key_by_id.get(key_id)
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
        key_ids: set[UUID] = set(
            await self.device_repository.list_key_ids_for_subscription(subscription.id)
        )
        key_by_id = await self._load_vpn_keys_by_ids(key_ids)
        restored = 0
        for key_id in key_ids:
            key = key_by_id.get(key_id)
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
        outputs_by_device = await self._list_device_key_outputs_for_devices(devices)
        out: list[SubscriptionDeviceOut] = []
        for device in devices:
            bundle_keys = outputs_by_device.get(device.id, [])
            out.append(
                SubscriptionDeviceOut(
                    id=device.id,
                    subscription_id=device.subscription_id,
                    vpn_key_ids=[item.vpn_key_id for item in bundle_keys],
                    transport_keys=bundle_keys,
                    hwid_hash=device.hwid_hash,
                    last_seen_at=device.last_seen_at,
                    user_agent=device.user_agent,
                    is_active=device.is_active,
                    created_at=device.created_at,
                    updated_at=device.updated_at,
                )
            )
        return out

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

        changed = False
        bundle = await self._load_device_bundle(device)
        for resolved_key in bundle.keys:
            key = resolved_key.key
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

    async def build_payload(
            self,
            raw_token: str,
            *,
            hwid: str | None = None,
            user_agent: str | None = None,
            if_none_match: str | None = None,
    ) -> tuple[str, str, bool, SubscriptionUserInfo | None]:
        t0 = time.perf_counter()

        token_hash = SubscriptionUtils.hash(raw_token)
        cache_ttl = max(0, int(self.settings.subscriptions.response_cache_ttl_sec))
        cache_key = redis_key.payload_cache(token_hash=token_hash, hwid=hwid)
        lock_key = redis_key.payload_build_lock(token_hash=token_hash, hwid=hwid)
        lock_acquired = False
        if cache_ttl > 0:
            cached_payload, cached_etag, cache_result = await self._read_payload_cache(cache_key)
            SUBSCRIPTION_CACHE_TOTAL.labels(result=cache_result).inc()
            if cached_etag:
                sub = await self.subscription_repository.get_by_any_token_hash(token_hash)
                cache_user_info = self._build_user_info(sub) if sub else None
                if if_none_match and if_none_match == cached_etag:
                    return "", cached_etag, True, cache_user_info
                if cached_payload is not None:
                    return cached_payload, cached_etag, False, cache_user_info
            lock_acquired = await self._acquire_payload_build_lock(lock_key)
            SUBSCRIPTION_CACHE_TOTAL.labels(
                result="lock_acquired" if lock_acquired else "lock_contended"
            ).inc()
            if not lock_acquired:
                waited_payload, waited_etag, waited_result = await self._wait_for_cached_payload(cache_key)
                SUBSCRIPTION_CACHE_TOTAL.labels(result=waited_result).inc()
                if waited_etag:
                    sub = await self.subscription_repository.get_by_any_token_hash(token_hash)
                    wait_user_info = self._build_user_info(sub) if sub else None
                    if if_none_match and if_none_match == waited_etag:
                        return "", waited_etag, True, wait_user_info
                    if waited_payload is not None:
                        return waited_payload, waited_etag, False, wait_user_info
        await self._enforce_rate_limit(token_hash)
        try:
            subscription = await self.subscription_repository.get_by_any_token_hash(token_hash)
            if not subscription:
                raise SubscriptionNotFound("subscription")

            if self._is_subscription_closed(subscription):
                user_info = self._build_user_info(subscription)
                return "", "", False, user_info

            self._validate_subscription(subscription, token_hash)

            now = datetime.now(timezone.utc)
            bundle = await self._resolve_device_bundle_for_request(
                subscription=subscription,
                hwid=hwid,
                user_agent=user_agent,
                now=now,
            )

            max_routes = max(1, min(10, int(self.settings.subscriptions.smart_route_max_count)))
            transport_results: list[TransportBuildResult] = []
            transport_diagnostics: dict[str, str] = {}
            for key in bundle.keys:
                result = await self._build_transport_routes(
                    subscription=subscription,
                    key=key,
                    max_routes=max_routes,
                )
                if result.routes:
                    transport_results.append(result)
                elif result.diagnostic_reason:
                    transport_diagnostics[key.transport] = result.diagnostic_reason

            if not transport_results:
                raise SubscriptionBuild(self._build_no_routes_message(transport_diagnostics))

            selected_routes = self._merge_transport_routes(
                subscription=subscription,
                transport_results=transport_results,
            )
            if not selected_routes:
                raise SubscriptionBuild(self._build_no_routes_message(transport_diagnostics))

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
                client_id=self._bundle_client_signature(bundle),
                placement_op_version=self._bundle_placement_signature(transport_results),
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

            user_info = self._build_user_info(subscription)

            SUBSCRIPTION_BUILD_DURATION.observe(time.perf_counter() - t0)

            if if_none_match and if_none_match == etag:
                return "", etag, True, user_info

            return payload, etag, False, user_info
        finally:
            if lock_acquired:
                await self._release_payload_build_lock(lock_key)

    def _build_user_info(self, subscription) -> SubscriptionUserInfo:
        plan = getattr(subscription, "plan", None)
        traffic_limit = int(getattr(plan, "traffic_limit_bytes", 0) or 0)
        used = int(getattr(subscription, "used_traffic_bytes", 0) or 0)

        expire_ts = 0
        if subscription.expires_at:
            expire_ts = int(subscription.expires_at.timestamp())

        return SubscriptionUserInfo(
            upload=0,
            download=used,
            total=traffic_limit,
            expire=expire_ts,
        )

    def _is_subscription_closed(self, subscription) -> bool:
        if not subscription.is_active:
            return True
        if subscription.expires_at and subscription.expires_at <= datetime.now(timezone.utc):
            return True
        return False

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
            placement_op_version: int | str | None = None,
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

    def _bundle_client_signature(self, bundle: ResolvedDeviceBundle) -> str:
        return ",".join(
            f"{key.transport}:{key.client_id}"
            for key in sorted(bundle.keys, key=lambda item: self._transport_priority(item.transport))
        )

    def _bundle_placement_signature(self, results: Iterable[TransportBuildResult]) -> str:
        signatures = [
            result.placement_signature
            for result in results
            if result.placement_signature
        ]
        return ",".join(signatures)

    def _build_no_routes_message(self, diagnostics: dict[str, str]) -> str:
        if not diagnostics:
            return "No available routes"
        details = ", ".join(
            f"{transport}={diagnostics[transport]}"
            for transport in sorted(diagnostics, key=self._transport_priority)
        )
        return f"No available routes [{details}]"

    async def _build_transport_routes(
            self,
            *,
            subscription,
            key: ResolvedDeviceKey,
            max_routes: int,
    ) -> TransportBuildResult:
        try:
            selected_backend_id, placement, allowed_backend_ids = await self._ensure_backend_placements_for_key(
                key_id=key.vpn_key_id,
                preferred_region=subscription.preferred_region,
                desired_replicas=max_routes,
                key_transport=key.transport,
            )
        except SubscriptionBuild as exc:
            return TransportBuildResult(
                key=key,
                routes=(),
                placement_signature=None,
                diagnostic_reason=self._map_transport_build_reason(str(exc)),
            )

        max_fetch = max(max_routes * 4, 12)
        allowed_backend_ids_sorted = sorted(allowed_backend_ids, key=str)
        route_rows = await self.route_repository.list_resolved_active(
            preferred_node_id=selected_backend_id,
            preferred_region=subscription.preferred_region,
            limit=max_fetch,
            backend_node_ids=allowed_backend_ids_sorted,
            node_seen_after=self._resolved_route_node_seen_after(),
        )
        entry_nodes_by_id = await self._entry_nodes_by_id(route_rows=route_rows)

        has_allowed = any(
            self._as_uuid(node.id) in allowed_backend_ids
            for _, node, _ in route_rows
        )
        if not has_allowed and allowed_backend_ids:
            route_rows = await self.route_repository.list_resolved_active(
                preferred_node_id=selected_backend_id,
                preferred_region=subscription.preferred_region,
                limit=max_fetch,
                backend_node_ids=allowed_backend_ids_sorted,
                node_seen_after=None,
            )
            entry_nodes_by_id = await self._entry_nodes_by_id(route_rows=route_rows)

        plan = subscription.plane
        whitelist_enabled = bool(plan and getattr(plan, "whitelist_enabled", False))
        entry_relay_enabled = bool(plan and getattr(plan, "entry_relay_enabled", False))

        resolved_routes: list[ResolvedSubscriptionRoute] = []
        seen_uris: set[str] = set()
        seen_logical_keys: set[tuple] = set()
        for route, node, transport_profile in route_rows:
            backend_node_id = self._as_uuid(node.id)
            if backend_node_id not in allowed_backend_ids:
                continue
            entry_node_id = self._route_entry_node_id(route)
            entry_node = entry_nodes_by_id.get(entry_node_id) if entry_node_id is not None else None

            if entry_node is not None:
                entry_role = getattr(entry_node, "role", "")
                if entry_role == ROLE_WHITELIST_ENTRY and not whitelist_enabled:
                    continue
                if entry_role == ROLE_ENTRY and not entry_relay_enabled:
                    continue

            transport_security = transport_profile.security
            transport_network = transport_profile.network
            if not self._is_route_compatible_with_key_transport(
                key_transport=key.transport,
                transport_security=transport_security,
                transport_network=transport_network,
            ):
                continue

            country_code, country_name = self._country_info_for_region(node.region)
            is_entry = entry_node is not None
            logical_key = self._route_country_transport_key(
                country_code=country_code,
                region=node.region,
                transport=key.transport,
                is_entry_route=is_entry,
                backend_node_id=backend_node_id,
            )
            if logical_key in seen_logical_keys:
                continue

            display = format_node_display_name(node_name=str(node.name), region=node.region)
            uri = self._build_route_uri(
                client_id=key.client_id,
                backend_node=node,
                public_node=entry_node,
                transport_profile=transport_profile,
                remark_override=display,
            )
            if uri is None or uri in seen_uris:
                continue

            seen_uris.add(uri)
            seen_logical_keys.add(logical_key)
            resolved_routes.append(
                ResolvedSubscriptionRoute(
                    route_id=self._as_uuid(route.id),
                    backend_node_id=backend_node_id,
                    vpn_key_id=key.vpn_key_id,
                    vpn_transport=key.transport,
                    client_id=key.client_id,
                    transport_security=transport_security,
                    transport_network=transport_network,
                    country_code=country_code,
                    country_name=country_name,
                    display_name=display,
                    is_entry_route=is_entry,
                    preferred_backend=backend_node_id == selected_backend_id,
                    selection_rank=len(resolved_routes),
                    uri=uri,
                    route=route,
                    node=node,
                    transport_profile=transport_profile,
                )
            )

        selected_routes = self.route_selector.select(
            routes=resolved_routes,
            preferred_backend_id=selected_backend_id,
            max_routes=max_routes,
        )
        if not selected_routes:
            return TransportBuildResult(
                key=key,
                routes=(),
                placement_signature=f"{key.transport}:pending=no-routes",
                diagnostic_reason="transport_no_routes",
            )

        return TransportBuildResult(
            key=key,
            routes=tuple(selected_routes),
            placement_signature=f"{key.transport}:{placement.op_version}",
            diagnostic_reason=None,
        )

    def _merge_transport_routes(
            self,
            *,
            subscription,
            transport_results: list[TransportBuildResult],
    ) -> list[ResolvedSubscriptionRoute]:
        merged: list[ResolvedSubscriptionRoute] = []
        seen_uris: set[str] = set()
        seen_logical_keys: set[tuple] = set()
        for result in transport_results:
            for route in result.routes:
                logical_key = self._route_country_transport_key(
                    country_code=route.country_code,
                    region=getattr(route.node, "region", None),
                    transport=route.vpn_transport,
                    is_entry_route=route.is_entry_route,
                    backend_node_id=route.backend_node_id,
                )
                if route.uri in seen_uris or logical_key in seen_logical_keys:
                    continue
                seen_uris.add(route.uri)
                seen_logical_keys.add(logical_key)
                merged.append(route)

        sorted_routes = sorted(
            merged,
            key=lambda item: self._presentation_sort_key(
                route=item,
                preferred_region=subscription.preferred_region,
            ),
        )
        return self._number_routes_display(sorted_routes)

    def _presentation_sort_key(
            self,
            *,
            route: ResolvedSubscriptionRoute,
            preferred_region: str | None,
    ) -> tuple[object, ...]:
        region = (route.node.region or "").strip().lower()
        preferred_region_norm = (preferred_region or "").strip().lower()
        country_name = route.country_name or (route.country_code or "Unknown")
        weight = getattr(route.route, "effective_weight", 0)
        return (
            1 if route.is_entry_route else 0,
            0 if preferred_region_norm and region == preferred_region_norm else 1,
            country_name,
            self._transport_priority(route.vpn_transport),
            0 if route.preferred_backend else 1,
            -int(weight or 0),
            route.selection_rank,
            route.uri,
        )

    @staticmethod
    def _map_transport_build_reason(message: str) -> str:
        if message in {"Node placement sync pending", "Backend placement sync pending"}:
            return "transport_pending"
        if message == "No available nodes":
            return "transport_backend_unhealthy"
        if message.startswith("No available "):
            return "transport_no_routes"
        return "transport_unavailable"

    def _country_info_for_region(self, region: str | None) -> tuple[str | None, str | None]:
        country_code = country_code_from_region(region)
        if not country_code:
            return None, None
        return country_code, COUNTRY_CODE_TO_NAME.get(country_code, country_code)

    def _route_country_transport_key(
            self,
            *,
            country_code: str | None,
            region: str | None,
            transport: str,
            is_entry_route: bool = False,
            backend_node_id: UUID | None = None,
    ) -> tuple:
        location_key = country_code or ((region or "").strip().lower() or None)
        norm_transport = self._normalize_transport_value(transport)
        if is_entry_route:
            return (location_key, norm_transport, True, "entry")
        return (location_key, norm_transport, False, str(backend_node_id) if backend_node_id else "")

    def _number_routes_display(
            self,
            routes: list[ResolvedSubscriptionRoute],
    ) -> list[ResolvedSubscriptionRoute]:
        from collections import defaultdict

        groups: dict[str | None, list[int]] = defaultdict(list)
        for idx, route in enumerate(routes):
            groups[route.country_code].append(idx)

        for _cc, indices in groups.items():
            direct_indices = [i for i in indices if not routes[i].is_entry_route]
            entry_indices = [i for i in indices if routes[i].is_entry_route]
            needs_number = len(direct_indices) > 1 or (direct_indices and entry_indices)

            if needs_number:
                for seq, i in enumerate(direct_indices, start=1):
                    route = routes[i]
                    base = format_node_display_name(
                        node_name=str(route.node.name), region=route.node.region,
                    )
                    new_name = f"{base} {seq}"
                    routes[i] = route.model_copy(update={
                        "display_name": new_name,
                        "uri": self._update_uri_remark(route.uri, new_name),
                    })

            for i in entry_indices:
                route = routes[i]
                base = format_node_display_name(
                    node_name=str(route.node.name), region=route.node.region,
                )
                new_name = f"{base} WL"
                routes[i] = route.model_copy(update={
                    "display_name": new_name,
                    "uri": self._update_uri_remark(route.uri, new_name),
                })

        return routes

    @staticmethod
    def _update_uri_remark(uri: str, new_remark: str) -> str:
        base, _, _ = uri.partition("#")
        return f"{base}#{urllib.parse.quote(new_remark)}"

    @staticmethod
    def _transport_label(transport: str) -> str:
        normalized = SubscriptionService._normalize_transport_value(transport)
        if normalized == VpnTransport.reality.value:
            return "Reality"
        if normalized == VpnTransport.ws.value:
            return "WS"
        if normalized == VpnTransport.xhttp.value:
            return "XHTTP"
        return normalized.upper()

    @staticmethod
    def _normalize_transport_value(transport: str) -> str:
        value = str(transport or "").strip()
        if not value:
            return ""
        if "." in value:
            value = value.rsplit(".", 1)[-1]
        return value.lower()

    @staticmethod
    def _transport_priority(transport: str) -> int:
        return TRANSPORT_PRIORITY.get(SubscriptionService._normalize_transport_value(transport), 99)

    def _subscription_bundle_transports(self, subscription) -> tuple[VpnTransport, ...]:
        preferred = self._infer_transport_from_profile_key(subscription.profile_key)
        ordered: list[VpnTransport] = []
        if preferred is not None:
            ordered.append(preferred)
        for transport in DEFAULT_SUBSCRIPTION_TRANSPORT_BUNDLE:
            if transport not in ordered:
                ordered.append(transport)
        return tuple(ordered)

    def _infer_transport_from_profile_key(self, profile_key: str | None) -> VpnTransport | None:
        if not profile_key:
            return None
        try:
            profile = ProfileRegistry.get(profile_key).profile
        except ProfileRegistryError:
            return None
        try:
            return self._infer_transport(profile.type)
        except HTTPException:
            return None

    def _infer_transport(self, profile_type: ProfileType) -> VpnTransport:
        if profile_type == ProfileType.ws_tls:
            return VpnTransport.ws
        if profile_type == ProfileType.reality_tcp:
            return VpnTransport.reality
        raise HTTPException(status_code=422, detail=f"Unsupported profile type: {profile_type}")

    def _describe_profile_registry_error(self, exc: ProfileRegistryError) -> str:
        available_keys = sorted(ProfileRegistry.all_keys())
        detail = str(exc)
        if not available_keys:
            return detail
        return f"{detail}. Available profile keys: {', '.join(available_keys)}"

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
            logger_sub.exception(
                "subscription_select_nodes_failed",
                key_id=str(key_id),
                preferred_region=preferred_region,
            )
            candidate_nodes = []
        candidate_nodes = [
            node for node in candidate_nodes
            if self._node_has_required_public_host(node=node)
        ]
        if not candidate_nodes and not placements_by_backend:
            raise SubscriptionBuild("No available nodes")

        if candidate_nodes:
            target_nodes = candidate_nodes[:desired_replicas]
            new_placement_ids: list[UUID] = []
            for node in target_nodes:
                node_id = self._as_uuid(str(node.id))
                if node_id in placements_by_backend:
                    continue
                created = await self.placement_repository.upsert_set_pending(
                    key_id=key_id,
                    backend_node_id=node_id,
                    desired_state=PlacementDesiredState.active.value,
                    sticky_until=None,
                    last_migration_reason="subscription_replica",
                )
                placements_by_backend[node_id] = created
                new_placement_ids.append(created.id)
            if new_placement_ids:
                await self.node_agent_transport.enqueue_for_placement_ids(new_placement_ids)
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
            raise SubscriptionBuild("Node placement sync pending")

        preferred_backend_id = self._as_uuid(preferred_placement.backend_node_id)
        allowed_backend_ids: set[UUID] = set(target_node_ids) if target_node_ids else set(placements_by_backend.keys())
        if not allowed_backend_ids:
            allowed_backend_ids = {preferred_backend_id}
        return preferred_backend_id, preferred_placement, allowed_backend_ids

    def _stale_after_sec(self) -> int:
        node_agent_settings = getattr(self.settings, "node_agent", None)
        return max(30, int(getattr(node_agent_settings, "stale_after_sec", 90)))

    def _resolved_route_node_seen_after(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(seconds=self._stale_after_sec() * 3)

    @staticmethod
    def _is_placement_synced(placement: UserPlacement) -> bool:
        applied_state = getattr(placement, "applied_state", "applied")
        if not isinstance(applied_state, str):
            applied_state = "applied"
        applied_version = getattr(placement, "applied_version", placement.op_version)
        if not isinstance(applied_version, int):
            applied_version = placement.op_version
        return applied_state == "applied" and applied_version == placement.op_version

    def _build_route_uri(
            self,
            *,
            client_id: str,
            backend_node: VpnNode | None = None,
            node: VpnNode | None = None,
            transport_profile,
            public_node: VpnNode | None = None,
            remark_override: str | None = None,
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
        node_display_name = remark_override or format_node_display_name(
            node_name=str(display_node.name),
            region=backend_node.region,
        )

        network = transport_profile.network
        security = transport_profile.security
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
        network = transport_profile.network
        security = transport_profile.security

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

    def _route_signature(self, *, route, node, transport_profile) -> str:
        route_updated = route.updated_at
        transport_updated = transport_profile.updated_at
        route_updated_at = (
            route_updated.isoformat()
            if isinstance(route_updated, datetime)
            else ""
        )
        transport_updated_at = (
            transport_updated.isoformat()
            if isinstance(transport_updated, datetime)
            else ""
        )
        return "|".join([
            str(route.id),
            str(route.health_status),
            str(route.effective_weight),
            str(node.id),
            self._resolve_route_host_for_transport(
                backend_node=node,
                transport_profile=transport_profile,
            ),
            str(transport_profile.id),
            str(transport_profile.port),
            route_updated_at,
            transport_updated_at,
        ])

    def _resolve_ws_public_host(self, node: VpnNode, *, prefer_node_domain: bool = False) -> str:
        if prefer_node_domain:
            node_domain = (node.public_domain or "").strip()
            if node_domain:
                return node_domain
        edge_domain = self.settings.edge.public_domain
        if edge_domain:
            return edge_domain
        return node.public_domain

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
            if public_node is not None:
                return public_node.public_domain or public_node.reality_ip or ""
            return visible_node.reality_ip
        return self._resolve_ws_public_host(
            visible_node,
            prefer_node_domain=public_node is not None,
        )

    def _node_has_required_public_host(self, *, node: VpnNode) -> bool:
        return bool(node.reality_ip or self._resolve_ws_public_host(node))


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

    async def _set_placement_desired_state(
            self,
            *,
            key_id: UUID,
            desired_state: PlacementDesiredState,
            reason: str,
    ) -> None:
        await self.placement_repository.set_desired_state_for_key(
            key_id=key_id,
            desired_state=desired_state.value,
            last_migration_reason=reason,
            updated_at=datetime.now(timezone.utc),
        )
        await self.node_agent_transport.enqueue_for_key_state(
            key_id=key_id,
            desired_state=desired_state.value,
        )

    def _hash_hwid(self, hwid: str) -> str:
        normalized = hwid.strip()
        if not normalized:
            raise SubscriptionHwidRequired()
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def _resolve_device_bundle_for_request(
            self,
            *,
            subscription,
            hwid: str | None,
            user_agent: str | None,
            now: datetime,
    ) -> ResolvedDeviceBundle:
        if not hwid:
            raise SubscriptionHwidRequired()

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
            return await self._ensure_device_key_bundle(
                subscription=subscription,
                device=device,
                now=now,
            )

        await self._lock_subscription_for_device_allocation(subscription.id)
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
            return await self._ensure_device_key_bundle(
                subscription=subscription,
                device=device,
                now=now,
            )

        plan = subscription.plan if hasattr(subscription, 'plan') else None
        if plan is None and subscription.plan_id:
            from services.plans.repository import PlanRepository
            plan_repo = PlanRepository(self.session)
            plan = await plan_repo.get_by_id(subscription.plan_id)
        if plan:
            effective_limit = plan.included_devices + (subscription.paid_device_slots or 0)
        else:
            effective_limit = subscription.max_devices or self.settings.subscriptions.max_devices_default
        current = await self.device_repository.count_active_for_subscription(subscription.id)
        if current >= effective_limit:
            raise SubscriptionDeviceLimitReached()

        valid_until = subscription.expires_at
        if valid_until is None:
            valid_until = now + timedelta(days=365)
        bundle_transports = self._subscription_bundle_transports(subscription)
        if not bundle_transports:
            raise SubscriptionBuild("No available key")

        primary_transport = bundle_transports[0]
        primary_key = await self._create_vpn_key_for_transport(
            subscription=subscription,
            transport=primary_transport,
            valid_until=valid_until,
        )

        try:
            device = await self.device_repository.create(
                SubscriptionDeviceCreate(
                    subscription_id=subscription.id,
                    hwid_hash=hwid_hash,
                    last_seen_at=now,
                    user_agent=user_agent,
                ).model_dump()
            )
        except IntegrityError:
            device = await self.device_repository.get_active_by_sub_and_hwid_hash(
                subscription_id=subscription.id,
                hwid_hash=hwid_hash,
            )
            if not device:
                raise
            return await self._ensure_device_key_bundle(
                subscription=subscription,
                device=device,
                now=now,
            )

        await self.device_key_repository.create(
            SubscriptionDeviceKeyCreate(
                subscription_device_id=device.id,
                vpn_key_id=primary_key.id,
                transport=primary_transport.value,
                is_primary=True,
            ).model_dump()
        )

        return await self._ensure_device_key_bundle(
            subscription=subscription,
            device=device,
            now=now,
        )

    async def _ensure_device_key_bundle(
            self,
            *,
            subscription,
            device: SubscriptionDevice,
            now: datetime,
    ) -> ResolvedDeviceBundle:
        required_transports = self._subscription_bundle_transports(subscription)
        bundle = await self._load_device_bundle(device)
        existing = {item.transport for item in bundle.keys}
        if all(transport.value in existing for transport in required_transports):
            return bundle

        await self._lock_subscription_for_device_allocation(subscription.id)
        bundle = await self._load_device_bundle(device)
        existing = {item.transport for item in bundle.keys}
        valid_until = subscription.expires_at or (now + timedelta(days=365))

        for idx, transport in enumerate(required_transports):
            if transport.value in existing:
                continue
            vpn_key = await self._create_vpn_key_for_transport(
                subscription=subscription,
                transport=transport,
                valid_until=valid_until,
            )
            try:
                await self.device_key_repository.create(
                    SubscriptionDeviceKeyCreate(
                        subscription_device_id=device.id,
                        vpn_key_id=vpn_key.id,
                        transport=transport.value,
                        is_primary=idx == 0 and not bundle.keys,
                    ).model_dump()
                )
            except IntegrityError:
                pass

        return await self._load_device_bundle(device)

    async def _load_device_bundle(self, device: SubscriptionDevice) -> ResolvedDeviceBundle:
        bundles = await self._load_device_bundles([device], binding_active_only=True)
        bundle = bundles.get(device.id)
        if bundle is not None:
            return bundle
        return ResolvedDeviceBundle(device=device, keys=())

    async def _create_vpn_key_for_transport(
            self,
            *,
            subscription,
            transport: VpnTransport,
            valid_until: datetime,
    ):
        # Derive traffic limit from subscription's plan, fallback to 0 (unlimited at key level)
        # when plan is set — enforcement happens at subscription level in traffic service
        plan = getattr(subscription, "plan", None)
        if plan and plan.traffic_limit_bytes and plan.traffic_limit_bytes > 0:
            traffic_limit_mb = max(1, plan.traffic_limit_bytes // (1024 * 1024))
        else:
            traffic_limit_mb = 0  # unlimited or plan-controlled

        key_internal = VpnKeyInternalCreate(
            user_id=subscription.user_id,
            protocol=VpnProtocol.vless,
            transport=transport,
            client_id=str(uuid4()),
            valid_until=valid_until,
            traffic_limit_mb=traffic_limit_mb,
            is_revoked=False,
            subscription_id=subscription.id,
        )
        return await self.vpn_key_repository.create(key_internal.model_dump())

    async def _load_device_bundles(
            self,
            devices: list[SubscriptionDevice],
            *,
            binding_active_only: bool,
    ) -> dict[UUID, ResolvedDeviceBundle]:
        if not devices:
            return {}

        bindings_by_device, key_by_id = await self._collect_device_key_material(
            devices,
            binding_active_only=binding_active_only,
        )
        bundles: dict[UUID, ResolvedDeviceBundle] = {}
        for device in devices:
            resolved: list[ResolvedDeviceKey] = []
            seen_transports: set[str] = set()
            for binding in bindings_by_device.get(device.id, []):
                key = key_by_id.get(binding.vpn_key_id)
                if not key:
                    continue
                transport = str(binding.transport or getattr(key, "transport", ""))
                if not transport or transport in seen_transports:
                    continue
                resolved.append(
                    ResolvedDeviceKey(
                        vpn_key_id=key.id,
                        transport=transport,
                        client_id=str(key.client_id),
                        is_primary=bool(binding.is_primary),
                        key=key,
                    )
                )
                seen_transports.add(transport)

            resolved.sort(
                key=lambda item: (
                    0 if item.is_primary else 1,
                    self._transport_priority(item.transport),
                    str(item.vpn_key_id),
                )
            )
            bundles[device.id] = ResolvedDeviceBundle(device=device, keys=tuple(resolved))
        return bundles

    async def _list_device_key_outputs_for_devices(
            self,
            devices: list[SubscriptionDevice],
    ) -> dict[UUID, list[SubscriptionDeviceKeyOut]]:
        if not devices:
            return {}

        bindings_by_device, _ = await self._collect_device_key_material(
            devices,
            binding_active_only=False,
        )
        outputs_by_device: dict[UUID, list[SubscriptionDeviceKeyOut]] = {}
        for device in devices:
            outputs: list[SubscriptionDeviceKeyOut] = []
            for binding in bindings_by_device.get(device.id, []):
                outputs.append(SubscriptionDeviceKeyOut.model_validate(binding))

            outputs.sort(
                key=lambda item: (
                    0 if item.is_primary else 1,
                    self._transport_priority(item.transport),
                    str(item.vpn_key_id),
                )
            )
            outputs_by_device[device.id] = outputs
        return outputs_by_device

    async def _collect_device_key_material(
            self,
            devices: list[SubscriptionDevice],
            *,
            binding_active_only: bool,
    ) -> tuple[dict[UUID, list[object]], dict[UUID, object]]:
        device_ids = [device.id for device in devices]
        bindings = await self.device_key_repository.list_by_device_ids(
            device_ids,
            active_only=binding_active_only,
        )
        bindings_by_device: dict[UUID, list[object]] = {}
        key_ids: list[UUID] = []
        for binding in bindings:
            bindings_by_device.setdefault(binding.subscription_device_id, []).append(binding)
            key_ids.append(binding.vpn_key_id)
        key_by_id = await self._load_vpn_keys_by_ids(key_ids)
        return bindings_by_device, key_by_id

    async def _load_vpn_keys_by_ids(self, key_ids: Iterable[UUID]) -> dict[UUID, object]:
        normalized = list(dict.fromkeys(key_ids))
        if not normalized:
            return {}

        keys = await self.vpn_key_repository.list_by_ids(key_ids=normalized)
        return {key.id: key for key in keys}

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
        index_key = redis_key.payload_cache_index(token_hash=token_hash)
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
        key = redis_key.rate_limit(token_hash)
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

    async def _invalidate_payload_cache_by_token_hash(self, token_hash: str) -> None:
        index_key = redis_key.payload_cache_index(token_hash=token_hash)
        try:
            keys = await self.redis.client.smembers(index_key)
            keys_to_delete = [
                key
                for key in keys
                if isinstance(key, str) and redis_key.is_payload_cache_key(key)
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
