from __future__ import annotations

import hashlib
import time
from datetime import timezone, datetime, timedelta
from typing import Iterable
from uuid import uuid4, UUID

from fastapi import HTTPException, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.repository import VpnNodeRepository
from services.routing.service import RoutingService
from services.users.repository import UserRepository
from services.vpn.keys.repository import VpnKeyRepository, KeyAssignmentRepository
from services.vpn.keys.schemas import VpnKeyInternalCreate, VpnProtocol, VpnTransport, AssignmentDesiredState
from services.vpn.subscriptions.constants import RATE_LIMIT_WINDOW_SEC, RATE_LIMIT_REQUESTS
from services.vpn.subscriptions.repository import SubscriptionRepository, SubscriptionDeviceRepository
from services.vpn.subscriptions.utils import SubscriptionUtils
from services.config import get_settings
from shared.database.session import AsyncDatabase
from shared.profiles.builder import VlessUriBuilder
from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.registry import ProfileRegistry
from shared.profiles.schemas import NodePublic, RealityTcpProfile, WsTlsProfile
from shared.profiles.types import ProfileType
from shared.metrics import SUBSCRIPTION_BUILD_DURATION
from shared.redis.client import RedisClient, get_redis_client

from services.vpn.subscriptions.schemas import (
    SubscriptionCreateIn,
    SubscriptionCreatedOut,
    SubscriptionRotateOut, SubscriptionInternalUpdate,
)
from services.vpn.subscriptions.schemas import (
    SubscriptionInternalCreate,
    SubscriptionInternalRotate,
)
from services.vpn.subscriptions.exceptions import (
    SubscriptionNotFound,
    SubscriptionInactive,
    SubscriptionExpired,
    SubscriptionTokenExpired,
    SubscriptionBuild,
    SubscriptionRateLimited,
    SubscriptionHwidRequired,
    SubscriptionDeviceLimitReached,
)


class SubscriptionService:
    def __init__(self, session: AsyncSession, redis: RedisClient):
        self.session = session
        self.redis = redis
        self.subscription_repository = SubscriptionRepository(session)
        self.device_repository = SubscriptionDeviceRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.routing_service = RoutingService(session)
        self.user_repository = UserRepository(session)
        self.vpn_key_repository = VpnKeyRepository(session)
        self.assignment_repository = KeyAssignmentRepository(session)

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

        # Legacy client_id in subscription is still used when HWID is disabled,
        # but may be overridden when binding to an existing key.
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

        valid_until = data.expires_at
        if valid_until is None:
            valid_until = datetime.now(timezone.utc) + timedelta(days=365)

        settings = get_settings()
        hwid_enabled = data.hwid_enabled
        if hwid_enabled is None:
            hwid_enabled = settings.subscriptions.require_hwid_default

        data = SubscriptionInternalCreate(
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
        subscription = await self.subscription_repository.create(
            data.model_dump()
        )

        vpn_key_id: UUID | None = None

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

            nodes = await self.node_repository.list()
            for node in nodes:
                if not getattr(node, "is_active", True):
                    continue
                if not getattr(node, "is_enabled", True):
                    continue
                await self.assignment_repository.upsert_assignment_set_pending(
                    key_id=vpn_key.id,
                    node_id=node.id,
                    desired_state=AssignmentDesiredState.present.value,
                )
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
            subscription_id, data.model_dump()
        )
        if not updated:
            raise SubscriptionNotFound

        await self._invalidate_rate_limit(sub.token_hash)
        await self._invalidate_rate_limit(new_hash)

        return SubscriptionRotateOut(token=new_raw)

    # ------------------------------------------------------------------
    # ACTIVATE / DEACTIVATE
    # ------------------------------------------------------------------

    async def deactivate(self, subscription_id: UUID) -> bool:
        subscription = await self.subscription_repository.get_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFound(subscription_id)

        data = SubscriptionInternalUpdate(
            is_active=False,
            updated_at=datetime.now(timezone.utc)
        )
        await self.subscription_repository.update_by_id(
            item_id=subscription.id, data=data.model_dump()
        )
        return True

    async def activate(self, subscription_id: UUID) -> bool:
        subscription = await self.subscription_repository.get_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFound(subscription_id)

        data = SubscriptionInternalUpdate(
            is_active = True,
            updated_at = datetime.now(timezone.utc)
        )
        await self.subscription_repository.update_by_id(
            item_id=subscription.id, data=data.model_dump()
        )
        return True

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

        nodes = await self.routing_service.select_nodes(
            preferred_region=subscription.preferred_region,
        )
        if not nodes:
            raise SubscriptionBuild("No available nodes")
        #todo Типизировать profile_key ws_tls_v1 or reality_tcp_v1
        profiles = self._select_profiles(subscription.profile_key)

        if vpn_key_id is not None:
            for node in nodes:
                await self.assignment_repository.upsert_assignment_set_pending(
                    key_id=vpn_key_id,
                    node_id=node.id,
                    desired_state=AssignmentDesiredState.present.value,
                )

        uris = self._build_uris(
            client_id=client_id,
            nodes=nodes,
            profiles=profiles,
        )

        if not uris:
            raise SubscriptionBuild("No available configs")

        payload = "\n".join(uris)
        etag = self._calc_etag(subscription, nodes, profiles, client_id=client_id)

        SUBSCRIPTION_BUILD_DURATION.observe(time.perf_counter() - t0)

        if if_none_match and if_none_match == etag:
            return "", etag, True

        return payload, etag, False

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

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
            node_public = NodePublic(
                domain=node.public_domain,
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
            payload: str
            if callable(model_dump_json):
                dumped = model_dump_json()
                if isinstance(dumped, bytes):
                    payload = dumped.decode()
                elif isinstance(dumped, str):
                    payload = dumped
                else:
                    dumped = None
            else:
                dumped = None

            if dumped is None:
                # Backward-compatible fallback for non-pydantic test doubles.
                payload = f"{getattr(profile, 'type', 'unknown')}:{getattr(profile, 'version', '')}"

            profile_parts.append(hashlib.sha256(payload.encode()).hexdigest())

        base = "|".join([
            str(sub.id),
            sub.updated_at.isoformat(),
            sub.profile_key or "",
            sub.preferred_region or "",
            client_id,
            ",".join(sorted(n.public_domain for n in nodes)),
            ",".join(sorted(profile_parts)),
        ])
        return hashlib.sha256(base.encode()).hexdigest()

    def _infer_transport(self, profile_type: ProfileType) -> VpnTransport:
        if profile_type == ProfileType.ws_tls:
            return VpnTransport.ws
        if profile_type == ProfileType.reality_tcp:
            return VpnTransport.tcp
        raise HTTPException(status_code=422, detail=f"Unsupported profile type: {profile_type}")

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
        Otherwise returns subscription.client_id (legacy) and vpn_key_id=None.
        """
        settings = get_settings()
        hwid_required = bool(subscription.hwid_enabled or settings.subscriptions.require_hwid_default)
        if not hwid and hwid_required:
            raise SubscriptionHwidRequired()

        if not hwid:
            # Legacy path: config uses a single key. Prefer explicit binding when present.
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

            # Hardening: if there is no key matching subscription.client_id, the generated config would
            # never work on nodes. Create such key on-demand.
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
            await self.device_repository.touch(device_id=device.id, last_seen_at=now, user_agent=user_agent)
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

        client_uuid = uuid4()
        key_internal = VpnKeyInternalCreate(
            user_id=subscription.user_id,
            protocol=VpnProtocol.vless,
            transport=transport,
            client_id=str(client_uuid),
            valid_until=valid_until,
            traffic_limit_mb=1000,
            is_revoked=False,
        )
        vpn_key = await self.vpn_key_repository.create(key_internal.model_dump())

        try:
            await self.device_repository.create({
                "subscription_id": subscription.id,
                "hwid_hash": hwid_hash,
                "vpn_key_id": vpn_key.id,
                "last_seen_at": now,
                "user_agent": user_agent,
            })
        except IntegrityError:
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

    # ------------------------------------------------------------------
    # RATE LIMIT (REDIS)
    # ------------------------------------------------------------------

    def _rl_key(self, token_hash: str) -> str:
        return f"sub:rl:{token_hash}"

    async def _enforce_rate_limit(self, token_hash: str) -> None:
        key = self._rl_key(token_hash)

        current = await self.redis.client.get(key)
        if current is None:
            await self.redis.client.setex(key, RATE_LIMIT_WINDOW_SEC, 1)
            return

        if int(current) >= RATE_LIMIT_REQUESTS:
            raise SubscriptionRateLimited()

        await self.redis.client.incr(key)

    async def _invalidate_rate_limit(self, token_hash: str) -> None:
        await self.redis.client.delete(self._rl_key(token_hash))

def get_subscription_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> SubscriptionService:
    return SubscriptionService(session, redis)
