from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.config import ProbeConfig, get_settings
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.probe.policy.repository import ProbePolicyRepository
from services.probe.schemas import (
    ProbeSyntheticClientIds,
    ProbeSyntheticDesiredBackends,
    ProbeSyntheticReconcileResult,
    ProbeTransportKind,
)
from services.routes.repository import RouteRepository
from services.users.repository import UserRepository
from services.users.schemas import UserInternalCreate
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.keys.schemas import (
    VpnKeyInternalCreate,
    VpnKeyInternalUpdate,
    VpnProtocol,
    VpnTransport,
)
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("probe-synthetic-reconciler"))


class ProbeSyntheticCredentialReconciler:
    """Reconciles synthetic probe credentials. Identity (client_ids, telegram_id,
    username) stays in env. Operational tunables (enabled, tick, key lifetime,
    traffic limit) come from `probe_policy` table on every tick.
    """

    _IDLE_WHEN_DISABLED_SEC = 300

    def __init__(
        self,
        *,
        probe_settings: ProbeConfig | None = None,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        service_factory: Callable[[AsyncSession], "_ProbeSyntheticCredentialService"] | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = probe_settings or get_settings().probe
        self._settings = settings
        self._synthetic_client_ids = ProbeSyntheticClientIds(
            reality=settings.synthetic_reality_client_id,
            ws=settings.synthetic_ws_client_id,
        )
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._service_factory = service_factory or (
            lambda session: _ProbeSyntheticCredentialService(
                session=session,
                probe_settings=settings,
                synthetic_client_ids=self._synthetic_client_ids,
            )
        )
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:probe_synthetic_credentials",
            ttl_sec=600,
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    def _is_configured(self) -> bool:
        return (
            self._settings.synthetic_user_telegram_id > 0
            and bool(self._synthetic_client_ids.configured_transports())
        )

    async def start(self) -> None:
        if not self._is_configured():
            logger.info(
                "probe_synthetic_reconcile_not_configured",
                synthetic_user_telegram_id=self._settings.synthetic_user_telegram_id,
                reality_client_id=self._synthetic_client_ids.reality is not None,
                ws_client_id=self._synthetic_client_ids.ws is not None,
            )
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def run_once(self) -> ProbeSyntheticReconcileResult | None:
        if not self._is_configured():
            return None
        async with self._session_maker() as session:
            policy = await ProbePolicyRepository(session).get_current()
            await session.commit()
        if not policy.synthetic_reconcile_enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return ProbeSyntheticReconcileResult()
            return await self._execute_tick(policy)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            sleep_sec = self._IDLE_WHEN_DISABLED_SEC
            try:
                async with self._session_maker() as session:
                    policy = await ProbePolicyRepository(session).get_current()
                    await session.commit()
                sleep_sec = max(30, int(policy.synthetic_reconcile_tick_sec))
                if policy.synthetic_reconcile_enabled:
                    async with self._tick_lock.hold() as acquired:
                        if acquired:
                            await self._execute_tick(policy)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("probe_synthetic_reconcile_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self, policy) -> ProbeSyntheticReconcileResult:
        async with self._session_maker() as session:
            service = self._service_factory(session)
            result = await service.reconcile(
                key_valid_days=policy.synthetic_key_valid_days,
                key_traffic_limit_mb=policy.synthetic_key_traffic_limit_mb,
            )
            await session.commit()
            if (
                result.processed_transports > 0
                or result.created_user
                or result.created_keys > 0
                or result.reactivated_keys > 0
                or result.activated_placements > 0
                or result.deactivated_placements > 0
            ):
                logger.info(
                    "probe_synthetic_reconcile_tick",
                    processed_transports=result.processed_transports,
                    created_user=result.created_user,
                    created_keys=result.created_keys,
                    reactivated_keys=result.reactivated_keys,
                    activated_placements=result.activated_placements,
                    deactivated_placements=result.deactivated_placements,
                )
            return result


class _ProbeSyntheticCredentialService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        probe_settings: ProbeConfig,
        synthetic_client_ids: ProbeSyntheticClientIds,
    ):
        self._settings = probe_settings
        self._synthetic_client_ids = synthetic_client_ids
        self._user_repository = UserRepository(session)
        self._key_repository = VpnKeyRepository(session)
        self._placement_repository = UserPlacementRepository(session)
        self._route_repository = RouteRepository(session)
        self._placement_transport = NodeAgentPlacementTransport(session)
        self._edge_public_domain = get_settings().edge.public_domain

    async def reconcile(
        self,
        *,
        key_valid_days: int,
        key_traffic_limit_mb: int,
    ) -> ProbeSyntheticReconcileResult:
        configured_client_ids = self._synthetic_client_ids.configured_transports()
        if not configured_client_ids:
            return ProbeSyntheticReconcileResult()

        desired_backends = await self._build_desired_backends()
        if desired_backends.is_empty():
            return ProbeSyntheticReconcileResult()

        user, created_user = await self._ensure_probe_user()
        result = ProbeSyntheticReconcileResult(created_user=created_user)

        for transport_kind, client_id in configured_client_ids.items():
            desired_backend_ids = desired_backends.backend_ids_for(transport_kind)
            if not desired_backend_ids:
                continue
            result.processed_transports += 1

            key, key_created, key_reactivated = await self._ensure_probe_key(
                user_id=user.id,
                transport_kind=transport_kind,
                client_id=client_id,
                valid_days=key_valid_days,
                traffic_limit_mb=key_traffic_limit_mb,
            )
            if key is None:
                continue
            if key_created:
                result.created_keys += 1
            if key_reactivated:
                result.reactivated_keys += 1

            placements = await self._placement_repository.list_by_key_id(
                key_id=key.id,
                active_only=True,
            )
            active_backend_ids = {
                placement.backend_node_id
                for placement in placements
                if placement.desired_state == PlacementDesiredState.active.value
            }
            to_activate = sorted(desired_backend_ids - active_backend_ids, key=str)
            to_deactivate = sorted(active_backend_ids - desired_backend_ids, key=str)

            changed_placement_ids: list[UUID] = []
            for backend_node_id in to_activate:
                placement = await self._placement_repository.upsert_set_pending(
                    key_id=key.id,
                    backend_node_id=backend_node_id,
                    desired_state=PlacementDesiredState.active.value,
                    sticky_until=None,
                    last_migration_reason="probe_synthetic_reconcile",
                )
                changed_placement_ids.append(placement.id)
                result.activated_placements += 1

            if to_deactivate:
                changed_placement_ids.extend(
                    await self._placement_repository.list_active_ids_for_key(
                        key_id=key.id,
                        desired_state=PlacementDesiredState.active.value,
                        backend_node_ids=to_deactivate,
                    )
                )
                deactivated = await self._placement_repository.set_desired_state_for_key(
                    key_id=key.id,
                    desired_state=PlacementDesiredState.inactive.value,
                    last_migration_reason="probe_synthetic_reconcile",
                    updated_at=datetime.now(timezone.utc),
                    backend_node_ids=to_deactivate,
                )
                result.deactivated_placements += int(deactivated)

            if changed_placement_ids:
                await self._placement_transport.enqueue_for_placement_ids(changed_placement_ids)

        return result

    async def _build_desired_backends(self) -> ProbeSyntheticDesiredBackends:
        route_rows = await self._route_repository.list_active_detailed(limit=5000)
        desired_backends = ProbeSyntheticDesiredBackends()

        for _route, node, transport_profile, _agent_state in route_rows:
            if node.role != "backend":
                continue
            if not node.is_enabled or node.is_draining:
                continue
            probe_transport_kind = self._probe_transport_kind(node=node, transport_profile=transport_profile)
            if probe_transport_kind is None:
                continue
            desired_backends.add_backend(transport_kind=probe_transport_kind, backend_id=node.id)

        return desired_backends

    def _probe_transport_kind(self, *, node, transport_profile) -> ProbeTransportKind | None:
        network = transport_profile.network
        security = transport_profile.security
        if security == "reality" and network == "tcp":
            host = node.reality_ip
            sni = transport_profile.reality_server_name
            public_key = transport_profile.reality_public_key
            short_id = transport_profile.reality_short_id
            if host and sni and public_key and short_id:
                return "reality"
            return None
        if security == "tls" and network == "ws":
            if self._edge_public_domain:
                return None
            host = node.public_domain
            if host:
                return "ws"
        return None

    async def _ensure_probe_user(self):
        telegram_id = int(self._settings.synthetic_user_telegram_id)
        if telegram_id <= 0:
            raise RuntimeError("probe synthetic reconcile requires PROBE_SYNTHETIC_USER_TELEGRAM_ID")
        user = await self._user_repository.get_by_telegram_id(telegram_id)
        if user is not None:
            return user, False
        created = await self._user_repository.create(
            UserInternalCreate(
                telegram_id=telegram_id,
                username=self._settings.synthetic_user_username or "probe-synthetic",
                tag="probe_synthetic",
                description="system synthetic probe user",
            ).model_dump()
        )
        return created, True

    async def _ensure_probe_key(
        self,
        *,
        user_id: UUID,
        transport_kind: ProbeTransportKind,
        client_id: str,
        valid_days: int,
        traffic_limit_mb: int,
    ):
        rows = await self._key_repository.list_by_client_ids(client_ids=[client_id], active_only=False)
        existing = rows[0] if rows else None
        valid_until = datetime.now(timezone.utc) + timedelta(days=max(1, int(valid_days)))
        if existing is None:
            created = await self._key_repository.create(
                VpnKeyInternalCreate(
                    user_id=user_id,
                    protocol=VpnProtocol.vless,
                    transport=VpnTransport(transport_kind),
                    client_id=client_id,
                    valid_until=valid_until,
                    traffic_limit_mb=max(1, int(traffic_limit_mb)),
                    is_revoked=False,
                ).model_dump()
            )
            return created, True, False

        if existing.transport != transport_kind:
            logger.warning(
                "probe_synthetic_key_transport_mismatch",
                client_id=client_id,
                expected_transport=transport_kind,
                actual_transport=existing.transport,
            )
            return None, False, False

        if existing.user_id != user_id:
            logger.warning(
                "probe_synthetic_key_user_mismatch",
                client_id=client_id,
                expected_user_id=str(user_id),
                actual_user_id=str(existing.user_id),
            )
            return None, False, False

        is_revoked = existing.is_revoked
        current_valid_until = existing.valid_until
        needs_reactivate = (
            not existing.is_active
            or is_revoked
            or current_valid_until is None
            or current_valid_until <= datetime.now(timezone.utc)
        )
        if not needs_reactivate:
            return existing, False, False

        updated = await self._key_repository.update_by_id(
            existing.id,
            VpnKeyInternalUpdate(
                is_active=True,
                is_revoked=False,
                valid_until=valid_until,
                traffic_limit_mb=max(1, int(traffic_limit_mb)),
            ).model_dump(exclude_unset=True),
        )
        return updated, False, True
