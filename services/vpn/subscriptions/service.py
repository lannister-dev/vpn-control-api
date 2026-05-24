from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
import urllib.parse
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.entry.repository import EntryBackendAssignmentRepository
from services.nodes.constants import ROLE_ENTRY, ROLE_WHITELIST_ENTRY
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.placements.models import UserPlacement
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
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
from services.vpn.subscriptions import redis_key
from services.vpn.subscriptions.constants import (
    DEFAULT_SUBSCRIPTION_TRANSPORT_BUNDLE,
    PAYLOAD_BUILD_LOCK_TTL_SEC,
    PAYLOAD_BUILD_WAIT_ATTEMPTS,
    PAYLOAD_BUILD_WAIT_DELAY_SEC,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SEC,
    TRANSPORT_PRIORITY,
    WHITELIST_SERVER_DESCRIPTION,
    WHITELIST_SUFFIX,
)
from services.vpn.subscriptions.exceptions import (
    SubscriptionBuild,
    SubscriptionDeviceLimitReached,
    SubscriptionExpired,
    SubscriptionHwidRequired,
    SubscriptionInactive,
    SubscriptionNotFound,
    SubscriptionRateLimited,
)
from services.vpn.subscriptions.models import Subscription, SubscriptionDevice
from services.vpn.subscriptions.repository import (
    SubscriptionDeviceKeyRepository,
    SubscriptionDeviceRepository,
    SubscriptionRepository,
)
from services.vpn.subscriptions.schemas import (
    ResolvedDeviceBundle,
    ResolvedDeviceKey,
    ResolvedSubscriptionRoute,
    SubscriptionCreatedOut,
    SubscriptionCreateIn,
    SubscriptionDeviceCreate,
    SubscriptionDeviceInternalUpdate,
    SubscriptionDeviceKeyCreate,
    SubscriptionDeviceKeyOut,
    SubscriptionDeviceOut,
    SubscriptionInternalCreate,
    SubscriptionInternalRotate,
    SubscriptionInternalUpdate,
    SubscriptionOut,
    SubscriptionRotateOut,
    SubscriptionUserInfo,
    TransportBuildResult,
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
from shared.profiles.constants import WS_TLS_DEFAULT_PATH
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
from shared.utils.logger import StructuredLogger
from shared.utils.node_display import (
    COUNTRY_CODE_TO_NAME,
    country_code_from_region,
    effective_zone,
    format_node_display_name,
)

logger_sub = StructuredLogger(logging.getLogger("subscription-build"))


class SubscriptionService:
    def __init__(
            self,
            session: AsyncSession,
            redis: RedisClient,
            *,
            nats_client=None,
    ):
        self.settings = get_settings()
        self.session = session
        self.redis = redis
        self._nats = nats_client
        self.subscription_repository = SubscriptionRepository(session)
        self.device_repository = SubscriptionDeviceRepository(session)
        self.device_key_repository = SubscriptionDeviceKeyRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.routing_service = RoutingService(session)
        self.placement_repository = UserPlacementRepository(session)
        self.node_agent_transport = NodeAgentPlacementTransport(session)
        self.route_repository = RouteRepository(session)
        self.entry_assignment_repository = EntryBackendAssignmentRepository(session)
        self.user_repository = UserRepository(session)
        self.vpn_key_repository = VpnKeyRepository(session)
        self.route_selector = RouteSelector[ResolvedSubscriptionRoute](
            get_backend_id=lambda item: item.backend_node_id,
            get_transport_key=lambda item: (item.transport_security, item.transport_network),
            get_route_id=lambda item: item.route_id,
            get_weight=lambda item: item.selection_score,
            get_entry_key=lambda item: item.entry_node_id,
        )

    async def create(self, data: SubscriptionCreateIn) -> SubscriptionCreatedOut:
        user = await self.user_repository.get_by_id(data.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        raw_token = SubscriptionUtils.generate()
        token_hash = SubscriptionUtils.hash(raw_token)

        uuid4()

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
    def _sub_to_out(sub, *, device_count: int | None = None) -> SubscriptionOut:
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
            device_count=device_count,
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

    async def list_route_assignments(self, subscription_id) -> list:
        from services.vpn.subscriptions.schemas import (
            SubscriptionNodeRef,
            SubscriptionRouteAssignmentOut,
        )
        rows = await self.subscription_repository.list_route_assignments(subscription_id)
        return [
            SubscriptionRouteAssignmentOut(
                device_id=r["device_id"],
                transport=r["transport"],
                last_assigned_at=r["last_assigned_at"],
                assignment_count=int(r["assignment_count"] or 0),
                entry=SubscriptionNodeRef(
                    node_id=r["entry_id"], name=r["entry_name"],
                    region=r["entry_region"], role=r["entry_role"],
                ),
                backend=SubscriptionNodeRef(
                    node_id=r["backend_id"], name=r["backend_name"],
                    region=r["backend_region"], role=r["backend_role"],
                ),
            )
            for r in rows
        ]

    async def node_distribution(self, *, since_hours: int | None = None) -> list:
        from datetime import datetime, timedelta, timezone

        from services.vpn.subscriptions.schemas import (
            NodeAssignmentDistributionOut,
            NodeAssignmentSlotOut,
        )
        since = None
        if since_hours and since_hours > 0:
            since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        rows = await self.subscription_repository.node_assignment_distribution(since=since)
        out = []
        for r in rows:
            as_entry = NodeAssignmentSlotOut(**r["as_entry"]) if r.get("as_entry") else None
            as_backend = NodeAssignmentSlotOut(**r["as_backend"]) if r.get("as_backend") else None
            total = max(
                as_entry.device_count if as_entry else 0,
                as_backend.device_count if as_backend else 0,
            )
            cap = int(r.get("capacity") or 0)
            out.append(NodeAssignmentDistributionOut(
                node_id=r["node_id"],
                name=r["name"],
                region=r["region"],
                role=r["role"],
                capacity=cap,
                as_entry=as_entry,
                as_backend=as_backend,
                total_device_count=total,
                load_pct=round(total / cap * 100, 1) if cap > 0 and total > 0 else None,
            ))
        return out

    async def list_active_nodes(self, subscription_id) -> list:
        from services.vpn.subscriptions.schemas import (
            SubscriptionActiveNodeOut,
            SubscriptionEntryRouteOut,
            SubscriptionNodeRef,
        )

        placements = await self.subscription_repository.list_active_backend_placements(subscription_id)
        if not placements:
            return []

        backend_ids = list({p["backend_id"] for p in placements})
        route_rows = await self.subscription_repository.list_entry_routes_for_backends(backend_ids)

        # Group entries by (backend_id, transport_kind) for matching to device-key transport.
        from collections import defaultdict
        kind_of = self._transport_kind_from_profile
        entries_by_backend: dict = defaultdict(list)
        for r in route_rows:
            kind = kind_of(network=r["network"], security=r["security"])
            entries_by_backend[r["backend_id"]].append({
                "entry": SubscriptionNodeRef(
                    node_id=r["entry_id"],
                    name=r["entry_name"],
                    region=r["entry_region"],
                    role=r["entry_role"],
                ),
                "transport_kind": kind,
                "health": r["health"],
                "weight": int(r["weight"] or 0),
            })

        out = []
        for p in placements:
            backend = SubscriptionNodeRef(
                node_id=p["backend_id"],
                name=p["backend_name"],
                region=p["backend_region"],
                role=p["backend_role"],
            )
            transport = p.get("transport")
            candidates = entries_by_backend.get(p["backend_id"], [])
            # Prefer entries matching the device-key transport; if none match,
            # fall back to all healthy candidates so the operator still sees
            # something useful.
            matching = [c for c in candidates if not transport or c["transport_kind"] == transport]
            chosen = matching if matching else candidates
            entries = [SubscriptionEntryRouteOut.model_validate(c) for c in chosen]
            out.append(SubscriptionActiveNodeOut(
                backend=backend,
                transport=transport,
                device_id=p["device_id"],
                placement_state=p.get("placement_state"),
                sticky_until=p.get("sticky_until"),
                entries=entries,
            ))
        return out

    async def _persist_route_assignments(
            self, *, subscription_id, device_id, selected_routes, now,
    ) -> None:
        """Persist primary (entry, backend, route) per transport for analytics.
        Picks the first route per transport (highest preference)."""
        seen: dict[str, dict] = {}
        for r in selected_routes:
            transport = getattr(r, "vpn_transport", "") or ""
            if not transport or transport in seen:
                continue
            entry_id = getattr(r, "entry_node_id", None)
            backend_id = getattr(r, "backend_node_id", None)
            if entry_id is None or backend_id is None:
                continue
            seen[transport] = {
                "subscription_device_id": device_id,
                "transport": transport,
                "entry_node_id": entry_id,
                "backend_node_id": backend_id,
                "route_id": getattr(r, "route_id", None),
            }
        if not seen:
            return
        try:
            await self.subscription_repository.upsert_route_assignments(
                subscription_id=subscription_id,
                assignments=list(seen.values()),
                now=now,
            )
        except Exception:
            # Never let analytics persistence block the subscription response.
            logger_sub.exception("route_assignment_upsert_failed")

    @staticmethod
    def _transport_kind_from_profile(*, network: str | None, security: str | None) -> str:
        n = (network or "").lower()
        s = (security or "").lower()
        if s == "reality" and n == "tcp":
            return "reality"
        if s == "tls" and n == "ws":
            return "ws"
        if s == "tls" and n == "grpc":
            return "xhttp"
        if s == "tls" and n == "tcp":
            return "tcp"
        return f"{s}-{n}" if s or n else ""

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
        counts = await self.device_repository.count_active_by_subscription_ids(
            [row.id for row in rows]
        )
        return [self._sub_to_out(row, device_count=counts.get(row.id, 0)) for row in rows]

    async def get_stats(self) -> tuple[int, int, int]:
        return await self.subscription_repository.count_stats()

    async def get_stats_with_history(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        now = await self.subscription_repository.count_stats()
        yesterday = await self.subscription_repository.count_stats_at(
            datetime.now(timezone.utc) - timedelta(days=1)
        )
        return now, yesterday

    async def list_paginated(
            self,
            *,
            active_only: bool = False,
            plan_id: UUID | None = None,
            limit: int = 50,
            offset: int = 0,
    ) -> tuple[list[SubscriptionOut], int]:
        rows, total = await self.subscription_repository.list_paginated(
            active_only=active_only, plan_id=plan_id, limit=limit, offset=offset,
        )
        return [self._sub_to_out(r) for r in rows], total

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
                    device_model=getattr(device, "device_model", None),
                    platform=getattr(device, "platform", None),
                    os_version=getattr(device, "os_version", None),
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
            device_model: str | None = None,
            platform: str | None = None,
            os_version: str | None = None,
            if_none_match: str | None = None,
            extra_etag_signature: str = "",
    ) -> tuple[str, str, bool, SubscriptionUserInfo | None]:
        t0 = time.perf_counter()

        token_hash = SubscriptionUtils.hash(raw_token)
        cache_ttl = max(0, int(self.settings.subscriptions.response_cache_ttl_sec))
        cache_suffix = f":{extra_etag_signature}" if extra_etag_signature else ""
        cache_key = redis_key.payload_cache(token_hash=token_hash, hwid=hwid) + cache_suffix
        lock_key = redis_key.payload_build_lock(token_hash=token_hash, hwid=hwid) + cache_suffix
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
                device_model=device_model,
                platform=platform,
                os_version=os_version,
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

            route_signatures = [
                self._route_signature(
                    route=item.route,
                    node=item.node,
                    transport_profile=item.transport_profile,
                )
                for item in selected_routes
            ]
            payload = await self._render_subscription_payload(
                selected_routes=selected_routes,
                client_id=bundle.keys[0].client_id if bundle.keys else "",
            )
            payload_bytes = len(payload.encode())
            if payload_bytes > max_payload_bytes:
                SUBSCRIPTION_PAYLOAD_GUARDRAIL_TOTAL.labels(result="overflow").inc()
                raise SubscriptionBuild("Subscription payload exceeds size limit")
            await self._persist_route_assignments(
                subscription_id=self._as_uuid(subscription.id),
                device_id=self._as_uuid(bundle.device.id),
                selected_routes=selected_routes,
                now=now,
            )
            # Auto-balance backend per key: pin user to the least-loaded backend
            # via entry_routing_override_backend_tag. Entry-node sing-box picks
            # this up via build_spec_for_node, so subsequent connections go
            # directly to the chosen backend without urltest leastPing.
            try:
                backend_live_loads = await self._fetch_live_backend_loads()
                nodes_by_id = await self._collect_backend_nodes_by_id(transport_results)
                for tr in transport_results:
                    route_backend_ids = await self.route_repository.list_backend_ids_with_entry_routes(
                        key_transport=tr.key.transport,
                    )
                    route_constrained = tuple(
                        bid for bid in tr.allowed_backend_ids if bid in set(route_backend_ids)
                    )
                    await self._rebalance_key_backend_override(
                        key=tr.key,
                        allowed_backend_ids=route_constrained or tr.allowed_backend_ids,
                        backend_live_loads=backend_live_loads,
                        nodes_by_id=nodes_by_id,
                    )
            except Exception:
                logger_sub.exception("backend_rebalance_failed")
            SUBSCRIPTION_PAYLOAD_SIZE_BYTES.observe(payload_bytes)
            etag = self._calc_etag(
                subscription,
                route_signatures,
                client_id=self._bundle_client_signature(bundle),
                placement_op_version=self._bundle_placement_signature(transport_results),
                extra_signature=extra_etag_signature,
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
        return bool(subscription.expires_at and subscription.expires_at <= datetime.now(timezone.utc))

    def _validate_subscription(self, subscription, token_hash: str) -> None:
        del token_hash
        now = datetime.now(timezone.utc)

        if not subscription.is_active:
            raise SubscriptionInactive()

        if subscription.expires_at and subscription.expires_at <= now:
            raise SubscriptionExpired()

    def _calc_etag(
            self,
            sub,
            route_signatures: Iterable[str],
            *,
            client_id: str,
            placement_op_version: int | str | None = None,
            extra_signature: str = "",
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
            extra_signature,
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
            allow_dead_entry=True,
        )
        entry_nodes_by_id = await self._entry_nodes_by_id(route_rows=route_rows)
        entries_by_zone = await self._safe_entries_by_zone()

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
                allow_dead_entry=True,
            )
            entry_nodes_by_id = await self._entry_nodes_by_id(route_rows=route_rows)

        wl_route_rows = await self.route_repository.list_resolved_active(
            preferred_node_id=None,
            preferred_region=None,
            limit=max_fetch,
            backend_node_ids=None,
            node_seen_after=None,
            allow_dead_entry=True,
        )
        existing_route_ids = {self._as_uuid(r.id) for r, _, _ in route_rows}
        wl_entry_ids = [
            self._route_entry_node_id(r)
            for r, _, _ in wl_route_rows
            if self._route_entry_node_id(r) is not None
        ]
        wl_entry_nodes = (
            await self.node_repository.list_by_ids(list(dict.fromkeys(wl_entry_ids)))
            if wl_entry_ids
            else []
        )
        wl_entry_role_by_id = {self._as_uuid(n.id): getattr(n, "role", "") for n in wl_entry_nodes}
        for row in wl_route_rows:
            wl_route, _wl_node, _wl_tp = row
            entry_id = self._route_entry_node_id(wl_route)
            if entry_id is None:
                continue
            if wl_entry_role_by_id.get(self._as_uuid(entry_id)) != ROLE_WHITELIST_ENTRY:
                continue
            if self._as_uuid(wl_route.id) in existing_route_ids:
                continue
            route_rows.append(row)
        entry_nodes_by_id = await self._entry_nodes_by_id(route_rows=route_rows)

        plan =subscription.plan
        whitelist_enabled = bool(plan and getattr(plan, "whitelist_enabled", False))
        entry_relay_enabled = bool(plan and getattr(plan, "entry_relay_enabled", False))

        backend_loads = await self._safe_call_counter(
            self.placement_repository.count_desired_active_by_backend_node
        )
        # Live entry load = actual sing-box connections per entry-node,
        # reported every ~10s by each node-agent into NATS KV
        # `entry-routing-stats`. Falls back to persisted assignment counts
        # when NATS is unavailable (gives reasonable distribution between
        # subscription polls of the same user).
        entry_loads = await self._fetch_live_entry_loads(
            exclude_subscription_id=self._as_uuid(subscription.id),
        )
        entry_user_loads = entry_loads

        resolved_routes: list[ResolvedSubscriptionRoute] = []
        seen_uris: set[str] = set()
        seen_logical_keys: set[tuple] = set()
        for route, node, transport_profile in route_rows:
            backend_node_id = self._as_uuid(node.id)
            raw_entry_node_id = self._route_entry_node_id(route)
            raw_entry_node = entry_nodes_by_id.get(raw_entry_node_id) if raw_entry_node_id is not None else None
            is_whitelist_route = (
                raw_entry_node is not None
                and getattr(raw_entry_node, "role", "") == ROLE_WHITELIST_ENTRY
            )
            if not is_whitelist_route and backend_node_id not in allowed_backend_ids:
                continue

            if raw_entry_node_id is not None:
                entry_node = self._select_entry_for_backend(
                    backend_node=node,
                    current_entry=raw_entry_node,
                    user_id=getattr(subscription, "user_id", None),
                    entries_by_zone=entries_by_zone,
                    entry_user_loads=entry_user_loads,
                )
                if entry_node is not None:
                    entry_nodes_by_id[self._as_uuid(entry_node.id)] = entry_node
                entry_node_id = self._as_uuid(entry_node.id) if entry_node is not None else None
            else:
                entry_node = None
                entry_node_id = None

            if entry_node is not None:
                entry_role = getattr(entry_node, "role", "")
                if entry_role == ROLE_WHITELIST_ENTRY and not whitelist_enabled:
                    continue
                if entry_role == ROLE_ENTRY and not entry_relay_enabled:
                    continue
            elif raw_entry_node_id is not None:
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
            backend_zone = effective_zone(
                explicit_zone=node.zone,
                region=node.region,
            )
            is_whitelist_entry = is_entry and entry_node.role == ROLE_WHITELIST_ENTRY
            logical_key = self._route_country_transport_key(
                country_code=country_code,
                region=node.region,
                transport=key.transport,
                is_entry_route=is_entry,
                backend_node_id=backend_node_id,
                entry_node_id=entry_node_id,
                zone=backend_zone,
                is_whitelist=is_whitelist_entry,
            )
            if logical_key in seen_logical_keys:
                continue

            display, server_description = self._subscription_display_for_route(
                backend_node=node,
                entry_node=entry_node,
            )
            uri = self._build_route_uri(
                client_id=key.client_id,
                backend_node=node,
                public_node=entry_node,
                transport_profile=transport_profile,
                remark_override=display,
                server_description=server_description,
            )
            if uri is None or uri in seen_uris:
                continue

            seen_uris.add(uri)
            seen_logical_keys.add(logical_key)
            effective_weight = int(getattr(route, "effective_weight", 0) or 0)
            backend_capacity = int(getattr(node, "capacity", 0) or 0)
            backend_load = int(backend_loads.get(backend_node_id, 0))
            backend_factor = self._capacity_factor(backend_load, backend_capacity)
            if entry_node_id is not None and entry_node is not None:
                entry_capacity = int(getattr(entry_node, "capacity", 0) or 0)
                entry_load = int(entry_loads.get(entry_node_id, 0))
                entry_factor = self._capacity_factor(entry_load, entry_capacity)
            else:
                entry_factor = 1.0
            selection_score = max(0.0, float(effective_weight)) * backend_factor * entry_factor
            resolved_routes.append(
                ResolvedSubscriptionRoute(
                    route_id=self._as_uuid(route.id),
                    backend_node_id=backend_node_id,
                    entry_node_id=entry_node_id,
                    vpn_key_id=key.vpn_key_id,
                    vpn_transport=key.transport,
                    client_id=key.client_id,
                    transport_security=transport_security,
                    transport_network=transport_network,
                    country_code=country_code,
                    country_name=country_name,
                    display_name=display,
                    is_entry_route=is_entry,
                    is_whitelist_route=(
                        entry_node is not None
                        and getattr(entry_node, "role", "") == ROLE_WHITELIST_ENTRY
                    ),
                    preferred_backend=backend_node_id == selected_backend_id,
                    selection_rank=len(resolved_routes),
                    effective_weight=effective_weight,
                    selection_score=selection_score,
                    uri=uri,
                    route=route,
                    node=node,
                    transport_profile=transport_profile,
                )
            )

        resolved_routes = await self._fill_entry_failover_substitutes(
            resolved_routes=resolved_routes,
            allowed_backend_ids=allowed_backend_ids,
            entry_nodes_by_id=entry_nodes_by_id,
            entries_by_zone=entries_by_zone,
            subscription=subscription,
            key=key,
            selected_backend_id=selected_backend_id,
            whitelist_enabled=whitelist_enabled,
            entry_relay_enabled=entry_relay_enabled,
            backend_loads=backend_loads,
            entry_loads=entry_loads,
            entry_user_loads=entry_user_loads,
        )

        # No seed — selector reshuffles every fetch by current live entry/backend
        # load. This is what makes the user actually migrate to a free entry/backend
        # on subscription refresh (the entry-aware `selection_score` does the
        # weighted lift). Stickiness comes from VLESS-line ORDER preserved in
        # Happ's local cache for already-connected sessions.
        selected_routes = self.route_selector.select(
            routes=resolved_routes,
            preferred_backend_id=selected_backend_id,
            max_routes=max_routes,
            seed=None,
        )
        if not selected_routes:
            return TransportBuildResult(
                key=key,
                routes=(),
                placement_signature=f"{key.transport}:pending=no-routes",
                diagnostic_reason="transport_no_routes",
                allowed_backend_ids=tuple(allowed_backend_ids),
            )

        return TransportBuildResult(
            key=key,
            routes=tuple(selected_routes),
            placement_signature=f"{key.transport}:{placement.op_version}",
            diagnostic_reason=None,
            allowed_backend_ids=tuple(allowed_backend_ids),
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
                    region=route.node.region,
                    transport=route.vpn_transport,
                    is_entry_route=route.is_entry_route,
                    backend_node_id=route.backend_node_id,
                    entry_node_id=route.entry_node_id,
                    zone=effective_zone(
                        explicit_zone=route.node.zone,
                        region=route.node.region,
                    ),
                    is_whitelist=route.is_whitelist_route,
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

    async def _fill_entry_failover_substitutes(
            self,
            *,
            resolved_routes: list[ResolvedSubscriptionRoute],
            allowed_backend_ids: set[UUID],
            entry_nodes_by_id: dict,
            entries_by_zone: dict[str, list[VpnNode]] | None = None,
            subscription,
            key: ResolvedDeviceKey,
            selected_backend_id: UUID,
            whitelist_enabled: bool,
            entry_relay_enabled: bool,
            backend_loads: dict,
            entry_loads: dict,
            entry_user_loads: dict | None = None,
    ) -> list[ResolvedSubscriptionRoute]:
        entry_user_loads = entry_user_loads or {}
        entries_by_zone = entries_by_zone or {}
        backends_with_routes = {r.backend_node_id for r in resolved_routes}
        missing_backends = [bid for bid in allowed_backend_ids if bid not in backends_with_routes]
        if not missing_backends:
            return resolved_routes

        try:
            assignments = await self.entry_assignment_repository.list_active_for_backends(
                missing_backends,
            )
        except Exception:
            return resolved_routes
        if not isinstance(assignments, list) or not assignments:
            return resolved_routes

        by_backend: dict[UUID, list[UUID]] = {}
        for a in assignments:
            by_backend.setdefault(a.backend_node_id, []).append(a.entry_node_id)
        if not by_backend:
            return resolved_routes

        seen_uris = {r.uri for r in resolved_routes}
        seen_logical_keys = {
            self._route_country_transport_key(
                country_code=r.country_code,
                region=r.node.region,
                transport=r.vpn_transport,
                is_entry_route=r.is_entry_route,
                backend_node_id=r.backend_node_id,
                entry_node_id=r.entry_node_id,
                zone=effective_zone(
                    explicit_zone=r.node.zone,
                    region=r.node.region,
                ),
                is_whitelist=r.is_whitelist_route,
            )
            for r in resolved_routes
        }
        seen_route_ids = {r.route_id for r in resolved_routes}

        augmented = list(resolved_routes)
        for backend_id, entry_ids in by_backend.items():
            try:
                rows = await self.route_repository.list_substitutes_for_backend(
                    backend_node_id=backend_id,
                    entry_node_ids=entry_ids,
                )
            except Exception:
                continue
            if not isinstance(rows, list):
                continue
            for route, node, transport_profile in rows:
                if self._as_uuid(route.id) in seen_route_ids:
                    continue
                raw_entry_node_id = self._route_entry_node_id(route)
                raw_entry_node = entry_nodes_by_id.get(raw_entry_node_id) if raw_entry_node_id else None
                if raw_entry_node is None and raw_entry_node_id is not None:
                    try:
                        raw_entry_node = await self.node_repository.get_by_id(raw_entry_node_id)
                    except Exception:
                        raw_entry_node = None
                    if raw_entry_node is not None:
                        entry_nodes_by_id[raw_entry_node_id] = raw_entry_node

                entry_node = self._select_entry_for_backend(
                    backend_node=node,
                    current_entry=raw_entry_node,
                    user_id=getattr(subscription, "user_id", None),
                    entries_by_zone=entries_by_zone,
                    entry_user_loads=entry_user_loads,
                )
                if entry_node is None:
                    continue
                entry_node_id = self._as_uuid(entry_node.id)
                entry_nodes_by_id[entry_node_id] = entry_node

                entry_role = getattr(entry_node, "role", "")
                if entry_role == ROLE_WHITELIST_ENTRY and not whitelist_enabled:
                    continue
                if entry_role == ROLE_ENTRY and not entry_relay_enabled:
                    continue

                backend_zone = effective_zone(
                    explicit_zone=getattr(node, "zone", None),
                    region=getattr(node, "region", None),
                )
                entry_zone = effective_zone(
                    explicit_zone=getattr(entry_node, "zone", None),
                    region=getattr(entry_node, "region", None),
                )
                if backend_zone != "unknown" and entry_zone != "unknown" and backend_zone != entry_zone:
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
                is_whitelist_entry = entry_node.role == ROLE_WHITELIST_ENTRY
                logical_key = self._route_country_transport_key(
                    country_code=country_code,
                    region=node.region,
                    transport=key.transport,
                    is_entry_route=True,
                    backend_node_id=backend_id,
                    entry_node_id=entry_node_id,
                    zone=backend_zone,
                    is_whitelist=is_whitelist_entry,
                )
                if logical_key in seen_logical_keys:
                    continue

                display, server_description = self._subscription_display_for_route(
                    backend_node=node,
                    entry_node=entry_node,
                )
                uri = self._build_route_uri(
                    client_id=key.client_id,
                    backend_node=node,
                    public_node=entry_node,
                    transport_profile=transport_profile,
                    remark_override=display,
                    server_description=server_description,
                )
                if uri is None or uri in seen_uris:
                    continue

                seen_uris.add(uri)
                seen_logical_keys.add(logical_key)
                seen_route_ids.add(self._as_uuid(route.id))
                effective_weight = int(getattr(route, "effective_weight", 0) or 0)
                backend_capacity = int(getattr(node, "capacity", 0) or 0)
                backend_load = int(backend_loads.get(backend_id, 0))
                backend_factor = self._capacity_factor(backend_load, backend_capacity)
                entry_capacity = int(getattr(entry_node, "capacity", 0) or 0)
                entry_load = int(entry_loads.get(entry_node_id, 0))
                entry_factor = self._capacity_factor(entry_load, entry_capacity)
                selection_score = (
                    max(0.0, float(effective_weight)) * backend_factor * entry_factor * 0.5
                )
                augmented.append(
                    ResolvedSubscriptionRoute(
                        route_id=self._as_uuid(route.id),
                        backend_node_id=backend_id,
                        entry_node_id=entry_node_id,
                        vpn_key_id=key.vpn_key_id,
                        vpn_transport=key.transport,
                        client_id=key.client_id,
                        transport_security=transport_security,
                        transport_network=transport_network,
                        country_code=country_code,
                        country_name=country_name,
                        display_name=display,
                        is_entry_route=True,
                        is_whitelist_route=(
                            getattr(entry_node, "role", "") == ROLE_WHITELIST_ENTRY
                        ),
                        preferred_backend=backend_id == selected_backend_id,
                        selection_rank=len(augmented),
                        effective_weight=effective_weight,
                        selection_score=selection_score,
                        uri=uri,
                        route=route,
                        node=node,
                        transport_profile=transport_profile,
                    )
                )
        return augmented

    @staticmethod
    async def _safe_call_counter(fn) -> dict:
        try:
            result = fn()
            if hasattr(result, "__await__"):
                result = await result
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        return {}

    @staticmethod
    def _capacity_factor(load: int, capacity: int) -> float:
        if capacity <= 0:
            return 1.0
        if load <= 0:
            return 1.0
        if load >= capacity:
            return 0.05
        remaining = capacity - load
        return max(0.05, remaining / capacity)

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
            entry_node_id: UUID | None = None,
            zone: str | None = None,
            is_whitelist: bool = False,
    ) -> tuple:
        location_key = country_code or ((region or "").strip().lower() or None)
        norm_transport = self._normalize_transport_value(transport)
        if is_entry_route:
            zone_key = (zone or "unknown").strip().lower() or "unknown"
            kind = "wl_entry" if is_whitelist else "entry"
            return (zone_key, norm_transport, kind)
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

    def _subscription_display_for_route(
            self,
            *,
            backend_node: VpnNode,
            entry_node: VpnNode | None,
    ) -> tuple[str, str | None]:
        if entry_node is None:
            return (
                format_node_display_name(
                    node_name=str(backend_node.name),
                    region=backend_node.region,
                ),
                None,
            )

        entry_role = getattr(entry_node, "role", "")
        if entry_role not in (ROLE_ENTRY, ROLE_WHITELIST_ENTRY):
            return (
                format_node_display_name(
                    node_name=str(backend_node.name),
                    region=backend_node.region,
                ),
                None,
            )

        zone_ref = getattr(backend_node, "zone_ref", None) or getattr(entry_node, "zone_ref", None)
        if zone_ref is not None and getattr(zone_ref, "is_active", True):
            emoji = (getattr(zone_ref, "emoji", "") or "").strip()
            name = (getattr(zone_ref, "name", "") or "").strip()
            base = f"{emoji} {name}".strip() if emoji else name
        else:
            base = ""
        if not base:
            base = format_node_display_name(
                node_name=str(backend_node.name),
                region=backend_node.region,
            )

        if entry_role == ROLE_WHITELIST_ENTRY:
            return f"{base}{WHITELIST_SUFFIX}", WHITELIST_SERVER_DESCRIPTION
        return base, None

    def _build_route_uri(
            self,
            *,
            client_id: str,
            backend_node: VpnNode | None = None,
            node: VpnNode | None = None,
            transport_profile,
            public_node: VpnNode | None = None,
            remark_override: str | None = None,
            server_description: str | None = None,
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
                    server_description=server_description,
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
            server_description=server_description,
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

    async def _render_subscription_payload(
        self,
        *,
        selected_routes,
        client_id: str,
    ) -> str:
        return "\n".join(item.uri for item in selected_routes)

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

    @staticmethod
    def _is_entry_usable(entry) -> bool:
        if entry is None:
            return False
        if not getattr(entry, "is_active", True):
            return False
        if not getattr(entry, "is_enabled", True):
            return False
        if getattr(entry, "is_draining", False):
            return False
        if getattr(entry, "is_virtual", False):
            return True
        try:
            insp = sa_inspect(entry)
        except Exception:
            insp = None
        if insp is None or "agent_state" not in getattr(insp, "unloaded", set()):
            agent = getattr(entry, "agent_state", None)
            if agent is not None and getattr(agent, "is_healthy", True) is False:
                return False
        return True

    @staticmethod
    def _user_hash_index(user_id, size: int, bucket: int | None = None) -> int:
        if size <= 0:
            return 0
        seed = str(user_id) if bucket is None else f"{user_id}:{bucket}"
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % size

    def _current_entry_bucket(self) -> int | None:
        bucket_sec = int(
            getattr(
                getattr(self.settings, "entry_relay", object()),
                "user_entry_bucket_seconds",
                0,
            ) or 0
        )
        if bucket_sec <= 0:
            return None
        return int(time.time()) // bucket_sec

    async def _safe_entries_by_zone(self) -> dict[str, list[VpnNode]]:
        fn = getattr(self.node_repository, "list_healthy_entries_by_zone", None)
        if fn is None:
            return {}
        try:
            result = fn()
            if hasattr(result, "__await__"):
                result = await result
        except Exception:
            return {}
        return result if isinstance(result, dict) else {}

    def _select_entry_for_backend(
            self,
            *,
            backend_node: VpnNode,
            current_entry: VpnNode | None,
            user_id,
            entries_by_zone: dict[str, list[VpnNode]],
            entry_user_loads: dict | None = None,
    ) -> VpnNode | None:
        zone = effective_zone(
            explicit_zone=getattr(backend_node, "zone", None),
            region=getattr(backend_node, "region", None),
        )
        candidates = list(entries_by_zone.get(zone) or [])
        if self._is_entry_usable(current_entry) and current_entry not in candidates:
            candidates.append(current_entry)
        required_role = getattr(current_entry, "role", None) if current_entry is not None else None
        if required_role:
            candidates = [e for e in candidates if getattr(e, "role", None) == required_role]
        candidates = [e for e in candidates if self._is_entry_usable(e)]
        if not candidates:
            return current_entry if self._is_entry_usable(current_entry) else None

        loads = entry_user_loads or {}
        bucket = self._current_entry_bucket()
        return min(
            candidates,
            key=lambda c: (
                int(loads.get(self._as_uuid(c.id), 0)),
                self._entry_tiebreak(user_id=user_id, entry_id=c.id, bucket=bucket),
            ),
        )

    async def _collect_backend_nodes_by_id(self, transport_results) -> dict:
        backend_ids = set()
        for tr in transport_results:
            backend_ids.update(getattr(tr, "allowed_backend_ids", ()) or ())
        if not backend_ids:
            return {}
        nodes = await self.node_repository.list_by_ids(list(backend_ids))
        return {self._as_uuid(n.id): n for n in nodes}

    async def _fetch_live_backend_loads(self) -> dict[str, int]:
        """Return {backend_tag: live_connection_count} aggregated across all
        entry-nodes from NATS KV (sing-box clash-API reports). Used to pin
        each user to the least-loaded backend via key override."""
        from services.routing.entry.constants import KV_STATS_BUCKET

        out: dict[str, int] = {}
        if self._nats is None:
            return out
        try:
            entries = await self._nats.kv_list_all(bucket=KV_STATS_BUCKET)
        except Exception:
            logger_sub.exception("live_backend_loads_fetch_failed")
            return out
        for raw in entries.values():
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            for tag, count in (payload.get("by_backend") or {}).items():
                out[tag] = out.get(tag, 0) + int(count)
        return out

    async def _rebalance_key_backend_override(
            self,
            *,
            key,
            allowed_backend_ids,
            backend_live_loads: dict[str, int],
            nodes_by_id: dict,
    ) -> None:
        if not allowed_backend_ids:
            return
        candidates: list[tuple[int, int, str]] = []
        for bid in allowed_backend_ids:
            node = nodes_by_id.get(bid)
            if not node or not getattr(node, "is_enabled", True):
                continue
            if getattr(node, "is_draining", False):
                continue
            tag = f"backend-{node.name}"
            load = int(backend_live_loads.get(tag, 0))
            tiebreak = self._backend_tiebreak(key_id=key.vpn_key_id, backend_id=node.id)
            candidates.append((load, tiebreak, tag))
        if not candidates:
            return
        candidates.sort()
        chosen_tag = candidates[0][2]
        try:
            vpn_key = await self.vpn_key_repository.get_by_id(key.vpn_key_id)
            if vpn_key is None:
                return
            current_tag = vpn_key.entry_routing_override_backend_tag
            current_in_candidates = any(c[2] == current_tag for c in candidates)
            if current_in_candidates and current_tag:
                current_load = next(c[0] for c in candidates if c[2] == current_tag)
                best_load = candidates[0][0]
                gap = current_load - best_load
                relative = gap / max(1, current_load)
                if gap <= 2 or relative < 0.30:
                    chosen_tag = current_tag
            if current_tag != chosen_tag:
                await self.vpn_key_repository.update_by_id(
                    key.vpn_key_id,
                    {"entry_routing_override_backend_tag": chosen_tag},
                )
        except Exception:
            logger_sub.exception("backend_override_update_failed", key_id=str(key.vpn_key_id))
            return
        backend_live_loads[chosen_tag] = backend_live_loads.get(chosen_tag, 0) + 1

    async def _fetch_live_entry_loads(
            self, *, exclude_subscription_id,
    ) -> dict[UUID, int]:
        """Return {entry_node_id: live_connection_count} from sing-box
        clash-api reports cached in NATS KV. Falls back to DB-assignment
        counts when NATS is unavailable or the bucket is empty."""
        from services.routing.entry.constants import KV_STATS_BUCKET

        live: dict[UUID, int] = {}
        if self._nats is not None:
            try:
                entries = await self._nats.kv_list_all(bucket=KV_STATS_BUCKET)
                for raw in entries.values():
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    node_id_raw = payload.get("node_id")
                    total = payload.get("total")
                    if node_id_raw and total is not None:
                        try:
                            node_uuid = UUID(str(node_id_raw))
                        except ValueError:
                            continue
                        live[node_uuid] = live.get(node_uuid, 0) + int(total)
            except Exception:
                logger_sub.exception("live_entry_loads_fetch_failed")

        if live:
            return live

        # Fallback: persisted assignment counts (lower fidelity but always
        # available; updates only on subscription fetch).
        try:
            return await self.subscription_repository.count_active_subs_by_entry(
                exclude_subscription_id=exclude_subscription_id,
            )
        except Exception:
            return {}

    @staticmethod
    def _entry_tiebreak(*, user_id, entry_id, bucket: int | None) -> int:
        seed = f"{user_id}:{bucket}:{entry_id}" if bucket is not None else f"{user_id}:{entry_id}"
        return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")

    @staticmethod
    def _backend_tiebreak(*, key_id, backend_id) -> int:
        seed = f"{key_id}:{backend_id}"
        return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")

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
            device_model: str | None = None,
            platform: str | None = None,
            os_version: str | None = None,
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
                device_model=device_model,
                platform=platform,
                os_version=os_version,
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
                device_model=device_model,
                platform=platform,
                os_version=os_version,
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
        plan_based = (plan.included_devices + (subscription.paid_device_slots or 0)) if plan else 0
        override = subscription.max_devices or 0
        effective_limit = max(override, plan_based) or self.settings.subscriptions.max_devices_default
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
                    device_model=device_model,
                    platform=platform,
                    os_version=os_version,
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
            with contextlib.suppress(IntegrityError):
                await self.device_key_repository.create(
                    SubscriptionDeviceKeyCreate(
                        subscription_device_id=device.id,
                        vpn_key_id=vpn_key.id,
                        transport=transport.value,
                        is_primary=idx == 0 and not bundle.keys,
                    ).model_dump()
                )

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
        result = await self.vpn_key_repository.create(key_internal.model_dump())
        from shared.monitoring.metrics import KEYS_CREATED_TOTAL
        KEYS_CREATED_TOTAL.labels(transport=transport or "unknown").inc()
        return result

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
        request: Request,
        session: AsyncSession = Depends(AsyncDatabase.get_session),
        redis: RedisClient = Depends(get_redis_client),
) -> SubscriptionService:
    nats_client = getattr(request.app.state, "nats_client", None)
    return SubscriptionService(session, redis, nats_client=nats_client)
