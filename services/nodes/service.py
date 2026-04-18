import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.entry.events import enqueue_pool_snapshots_for_backend
from services.nodes.constants import (
    ALLOWED_NODE_ROLES,
    DEFAULT_NODE_ROLE,
    DRAIN_REASON_UNHEALTHY_HEARTBEAT,
    HEARTBEAT_DETAILS_KEY,
    ROLE_BACKEND,
)
from services.nodes.exceptions import (
    AdminNodeAlreadyBootstrappedError,
    AdminNodeCreateError,
    AdminNodeNotFoundError,
    NodeBootstrapConflictError,
)
from services.nodes.models import VpnNode
from services.nodes.repository import (
    NodeAgentIdentityRepository,
    NodeAgentStateRepository,
    VpnNodeRepository,
)
from services.config import get_settings
from services.nodes.schemas import (
    AdminNodeCreateIn,
    AdminNodeCreateOut,
    AdminNodeRotateBootstrapOut,
    NodeAgentDetails,
    NodeHeartbeatMeta,
    NodeAgentStateCreate,
    NodeAgentStateUpdate,
    NodeHeartbeatIn,
    NodeAgentInitialOut,
    NodeSyncDetails,
    NodeSyncReportIn,
    VpnNodeCreate,
    VpnNodeOut,
)
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import (
    NODE_BOOTSTRAP_TOTAL,
)
from shared.utils.logger import StructuredLogger

logger_node = StructuredLogger(logging.getLogger("node-service"))


class VpnNodeService:
    def __init__(self, session: AsyncSession):
        self.vpn_node_repository = (
            VpnNodeRepository(session)
        )
        self.node_agent_state_repository = (
            NodeAgentStateRepository(session)
        )
        self.node_agent_identity_repository = (
            NodeAgentIdentityRepository(session)
        )
        node_agent_settings = get_settings().node_agent
        self.sync_report_debounce_sec = max(0, int(node_agent_settings.sync_report_debounce_sec))
        self.auth_token_rotation_grace_sec = max(
            0,
            int(node_agent_settings.auth_token_rotation_grace_sec),
        )
        self.bootstrap_allow_create = bool(node_agent_settings.bootstrap_allow_create)
        self.heartbeat_unhealthy_drain_threshold = max(
            1, int(node_agent_settings.heartbeat_unhealthy_drain_threshold)
        )
        self.heartbeat_healthy_undrain_threshold = max(
            1, int(node_agent_settings.heartbeat_healthy_undrain_threshold)
        )

    async def initial(
            self,
            *,
            source_ip: str,
            node_key: str,
            node_role: str | None,
            agent_instance_id: UUID,
    ) -> NodeAgentInitialOut:
        """
        Initial node identity bootstrap.

        - strict node identity source: node_key
        - idempotent
        - strict per-agent auth token issuance by agent_instance_id
        """

        normalized_node_key = node_key.strip()
        if not normalized_node_key:
            raise ValueError("node_key cannot be empty")
        normalized_node_role = self._normalize_bootstrap_node_role(node_role)
        node = await self.vpn_node_repository.get_by_node_key(normalized_node_key)
        if node is None:
            # Admin-created nodes have node_key=None; match by name since
            # AGENT_NODE_KEY == spec.nodeName == node.name from the installer.
            candidate = await self.vpn_node_repository.get_one_by(name=normalized_node_key)
            if candidate is not None and candidate.node_key is None:
                node = candidate
                await self.vpn_node_repository.update_by_id(
                    node.id,
                    {"node_key": normalized_node_key, "internal_wg_ip": source_ip},
                )
                NODE_BOOTSTRAP_TOTAL.labels(result="recovered_by_name").inc()
                logger_node.info(
                    "admin-created node claimed by agent",
                    node_id=str(node.id),
                    name=node.name,
                )
        if node is None:
            same_ip_nodes = await self.vpn_node_repository.list_by_internal_ip(source_ip=source_ip)
            if len(same_ip_nodes) == 1:
                node = same_ip_nodes[0]
                await self.vpn_node_repository.update_by_id(
                    node.id,
                    {"node_key": normalized_node_key},
                )
                NODE_BOOTSTRAP_TOTAL.labels(result="recovered_by_source_ip").inc()
                logger_node.warning(
                    "node bootstrap recovered existing node by source ip",
                    node_id=str(node.id),
                    source_ip=source_ip,
                )
            elif len(same_ip_nodes) > 1:
                NODE_BOOTSTRAP_TOTAL.labels(result="recovery_ambiguous").inc()
                raise NodeBootstrapConflictError(
                    "Ambiguous node recovery: multiple nodes share source IP. "
                    "Set AGENT_NODE_KEY to existing node key to avoid creating a new node."
                )

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        previous_token_valid_until = datetime.now(timezone.utc) + timedelta(
            seconds=self.auth_token_rotation_grace_sec,
        )

        if node is None:
            if not self.bootstrap_allow_create:
                NODE_BOOTSTRAP_TOTAL.labels(result="create_disabled").inc()
                raise NodeBootstrapConflictError(
                    "Unknown node identity and auto-create is disabled. "
                    "Set stable AGENT_NODE_KEY for this node or enable NODE_BOOTSTRAP_ALLOW_CREATE."
                )
            create_schema = VpnNodeCreate(
                name=f"node-{source_ip.replace('.', '-')}",
                role=normalized_node_role,
                region="unknown",
                public_domain="",
                internal_wg_ip=source_ip,
                node_key=normalized_node_key,
                xray_api_port=10085,
                agent_port=9000,
                auth_token_hash=token_hash,
            )
            create_schema.name = self._build_node_name(source_ip=source_ip, node_key=normalized_node_key)

            node = await self.vpn_node_repository.create(
                create_schema.model_dump()
            )
            NODE_BOOTSTRAP_TOTAL.labels(result="created").inc()
        await self.node_agent_identity_repository.upsert_token(
            node_id=node.id,
            agent_instance_id=agent_instance_id,
            token_hash=token_hash,
            previous_token_valid_until=previous_token_valid_until,
            full_resync_required=True,
        )
        NODE_BOOTSTRAP_TOTAL.labels(result="identity_issued").inc()

        return NodeAgentInitialOut(
            node_id=str(node.id),
            node_auth_token=raw_token,
            agent_instance_id=str(agent_instance_id),
            full_resync_required=True,
        )

    def _normalize_bootstrap_node_role(self, node_role: str | None) -> str:
        if node_role is None:
            return DEFAULT_NODE_ROLE
        if node_role in ALLOWED_NODE_ROLES:
            return node_role
        return DEFAULT_NODE_ROLE

    async def handle_heartbeat(
            self,
            node: VpnNode,
            payload: NodeHeartbeatIn,
    ) -> None:
        now = datetime.now(timezone.utc)
        effective_is_healthy = self._effective_heartbeat_health(payload)
        existing_state = await self.node_agent_state_repository.get_one_by(node_id=node.id)
        existing_details = self._normalize_details(
            existing_state.details if existing_state is not None else None
        )
        details = NodeAgentDetails(
            runtime=payload.details.runtime,
            stats=payload.details.stats,
        )
        heartbeat_meta = self._next_heartbeat_meta(
            base_details=existing_details,
            is_healthy=effective_is_healthy,
        )
        should_drain = (
            not effective_is_healthy
            and not node.is_draining
            and heartbeat_meta.consecutive_unhealthy >= self.heartbeat_unhealthy_drain_threshold
        )
        if should_drain:
            await self.vpn_node_repository.update_by_id(
                node.id,
                {"is_draining": True},
            )
            node.is_draining = True
            heartbeat_meta.drain_reason = DRAIN_REASON_UNHEALTHY_HEARTBEAT
            heartbeat_meta.drained_at = now
            if node.role == ROLE_BACKEND:
                await enqueue_pool_snapshots_for_backend(
                    self.vpn_node_repository.session, node.id
                )
            logger_node.info(
                "node set to draining after unhealthy heartbeat threshold",
                node_id=str(node.id),
                threshold=self.heartbeat_unhealthy_drain_threshold,
                consecutive_unhealthy=heartbeat_meta.consecutive_unhealthy,
            )
        should_undrain = (
            effective_is_healthy
            and node.is_draining
            and node.is_active
            and node.is_enabled
            and heartbeat_meta.drain_reason in (DRAIN_REASON_UNHEALTHY_HEARTBEAT, None)
            and heartbeat_meta.consecutive_healthy >= self.heartbeat_healthy_undrain_threshold
        )
        if should_undrain:
            await self.vpn_node_repository.update_by_id(
                node.id,
                {"is_draining": False},
            )
            node.is_draining = False
            heartbeat_meta.drain_reason = None
            heartbeat_meta.drained_at = None
            if node.role == ROLE_BACKEND:
                await enqueue_pool_snapshots_for_backend(
                    self.vpn_node_repository.session, node.id
                )
            logger_node.info(
                "node restored from draining after healthy heartbeat threshold",
                node_id=str(node.id),
                threshold=self.heartbeat_healthy_undrain_threshold,
                consecutive_healthy=heartbeat_meta.consecutive_healthy,
            )
        details_data = details.model_dump(mode="json", exclude_none=True)
        details_data[HEARTBEAT_DETAILS_KEY] = heartbeat_meta.model_dump(
            mode="json",
            exclude_none=True,
        )
        state = NodeAgentStateCreate(
            node_id=node.id,
            agent_version=payload.agent_version,
            is_healthy=effective_is_healthy,
            last_seen_at=now,
            last_sync_at=None,
            details=details_data,
        )
        await self.node_agent_state_repository.upsert(state.model_dump(exclude_none=True))

    async def handle_sync_report(
            self,
            *,
            node: VpnNode,
            payload: NodeSyncReportIn,
    ) -> bool:
        now = datetime.now(timezone.utc)
        state = await self.node_agent_state_repository.get_one_by(node_id=node.id)
        if self._is_debounced_sync_report(
                state=state,
                payload=payload,
                now=now,
        ):
            return False
        base = state.details if state is not None else {}
        if not isinstance(base, dict):
            base = {}
        details = NodeAgentDetails.model_validate(base)
        details.sync = NodeSyncDetails(
            synced_count=payload.synced_count,
            reported_at=now,
            inventory_hash=payload.inventory_hash,
            inventory_count=payload.inventory_count,
            full_resync_completed=payload.full_resync_completed,
        )
        details_data = details.model_dump(mode="json", exclude_none=True)
        if state is None:
            create_state = NodeAgentStateCreate(
                node_id=node.id,
                agent_version="unknown",
                is_healthy=True,
                last_seen_at=now,
                last_sync_at=now,
                last_config_version=payload.config_version,
                details=details_data,
            )
            await self.node_agent_state_repository.upsert(
                create_state.model_dump(exclude_none=True)
            )
            await self.node_agent_identity_repository.clear_full_resync_required_for_node(
                node_id=node.id,
            )
            return True
        else:
            update_state = NodeAgentStateUpdate(
                last_sync_at=now,
                last_config_version=payload.config_version,
                details=details_data,
            )
            await self.node_agent_state_repository.update_by_node_id(
                node_id=node.id,
                data=update_state.model_dump(exclude_none=True),
            )
            await self.node_agent_identity_repository.clear_full_resync_required_for_node(
                node_id=node.id,
            )
            return True

    def _is_debounced_sync_report(
            self,
            *,
            state,
            payload: NodeSyncReportIn,
            now: datetime,
    ) -> bool:
        if self.sync_report_debounce_sec <= 0 or state is None:
            return False
        if payload.config_version is None:
            return False

        state_last_config_version = state.last_config_version
        state_last_sync_at = self._to_utc_or_none(state.last_sync_at)
        if state_last_config_version != payload.config_version or state_last_sync_at is None:
            return False

        elapsed_sec = (now - state_last_sync_at).total_seconds()
        if elapsed_sec >= self.sync_report_debounce_sec:
            return False

        details_raw = state.details if isinstance(state.details, dict) else {}
        existing_details = NodeAgentDetails.model_validate(details_raw)
        existing_sync = existing_details.sync
        existing_synced_count = existing_sync.synced_count if existing_sync else None
        if existing_synced_count != payload.synced_count:
            return False
        existing_inventory_hash = existing_sync.inventory_hash if existing_sync else None
        if existing_inventory_hash != payload.inventory_hash:
            return False
        existing_inventory_count = existing_sync.inventory_count if existing_sync else None
        if existing_inventory_count != payload.inventory_count:
            return False
        existing_full_resync_completed = (
            existing_sync.full_resync_completed if existing_sync else None
        )
        if existing_full_resync_completed != payload.full_resync_completed:
            return False
        return True

    @staticmethod
    def _effective_heartbeat_health(payload: NodeHeartbeatIn) -> bool:
        return bool(payload.is_healthy and payload.details.runtime.ready)

    @classmethod
    def _next_heartbeat_meta(
            cls,
            *,
            base_details: dict[str, object],
            is_healthy: bool,
    ) -> NodeHeartbeatMeta:
        heartbeat_raw = base_details.get(HEARTBEAT_DETAILS_KEY)
        heartbeat_data = heartbeat_raw if isinstance(heartbeat_raw, dict) else {}

        consecutive_unhealthy = cls._safe_int(heartbeat_data.get("consecutive_unhealthy"))
        consecutive_healthy = cls._safe_int(heartbeat_data.get("consecutive_healthy"))
        drain_reason_raw = heartbeat_data.get("drain_reason")
        drain_reason = (
            drain_reason_raw
            if isinstance(drain_reason_raw, str) and drain_reason_raw.strip()
            else None
        )

        if is_healthy:
            consecutive_healthy += 1
            consecutive_unhealthy = 0
        else:
            consecutive_unhealthy += 1
            consecutive_healthy = 0

        return NodeHeartbeatMeta(
            consecutive_unhealthy=consecutive_unhealthy,
            consecutive_healthy=consecutive_healthy,
            drain_reason=drain_reason,
        )

    @staticmethod
    def _normalize_details(raw: object) -> dict[str, object]:
        if isinstance(raw, dict):
            return raw
        return {}

    @staticmethod
    def _safe_int(raw: object) -> int:
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _to_utc_or_none(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _build_node_name(*, source_ip: str, node_key: str) -> str:
        base = f"node-{source_ip.replace('.', '-')}"
        suffix = node_key[:8]
        candidate = f"{base}-{suffix}"
        return candidate[:64]

    # ------------------------------------------------------------------
    # Admin flow: create a pending node + mint a one-shot bootstrap token.
    # ------------------------------------------------------------------

    async def admin_create_node(self, payload: AdminNodeCreateIn) -> AdminNodeCreateOut:
        role = payload.role.strip()
        if role not in ALLOWED_NODE_ROLES:
            raise AdminNodeCreateError(
                f"role must be one of: {', '.join(sorted(ALLOWED_NODE_ROLES))}"
            )
        name = payload.name.strip()
        if not name:
            raise AdminNodeCreateError("name is required")

        existing = await self.vpn_node_repository.get_one_by(name=name)
        if existing is not None:
            raise AdminNodeCreateError(f"node with name '{name}' already exists")

        raw_token, token_hash = self._mint_bootstrap_token()
        expires_at = self._bootstrap_token_expires_at()

        create_schema = VpnNodeCreate(
            name=name,
            role=role,
            region=payload.region.strip() or "unknown",
            public_domain=payload.public_domain.strip(),
            reality_ip=(payload.reality_ip or "").strip() or None,
            internal_wg_ip=payload.internal_wg_ip.strip(),
            node_key=None,
            auth_token_hash=token_hash,
            capacity=payload.capacity,
        )
        node = await self.vpn_node_repository.create(
            {
                **create_schema.model_dump(),
                "bootstrap_token_expires_at": expires_at,
                "bootstrapped_at": None,
            }
        )
        NODE_BOOTSTRAP_TOTAL.labels(result="admin_pending_created").inc()
        logger_node.info(
            "admin created pending node",
            node_id=str(node.id),
            name=node.name,
            role=node.role,
        )
        return AdminNodeCreateOut(
            node=VpnNodeOut.model_validate(node),
            bootstrap_token=raw_token,
            bootstrap_token_expires_at=expires_at,
            install_command=self._render_install_command(raw_token),
        )

    async def admin_rotate_bootstrap_token(
            self,
            node_id: UUID,
    ) -> AdminNodeRotateBootstrapOut:
        node = await self.vpn_node_repository.get_by_id(node_id)
        if node is None or not node.is_active:
            raise AdminNodeNotFoundError(f"node {node_id} not found")
        if node.bootstrapped_at is not None:
            raise AdminNodeAlreadyBootstrappedError(
                f"node {node_id} already bootstrapped at {node.bootstrapped_at.isoformat()}"
            )

        raw_token, token_hash = self._mint_bootstrap_token()
        expires_at = self._bootstrap_token_expires_at()
        await self.vpn_node_repository.update_by_id(
            node.id,
            {
                "auth_token_hash": token_hash,
                "bootstrap_token_expires_at": expires_at,
            },
        )
        NODE_BOOTSTRAP_TOTAL.labels(result="admin_token_rotated").inc()
        return AdminNodeRotateBootstrapOut(
            node_id=node.id,
            bootstrap_token=raw_token,
            bootstrap_token_expires_at=expires_at,
            install_command=self._render_install_command(raw_token),
        )

    async def mark_bootstrapped(self, node: VpnNode) -> datetime:
        now = datetime.now(timezone.utc)
        await self.vpn_node_repository.update_by_id(
            node.id,
            {
                "bootstrapped_at": now,
                "bootstrap_token_expires_at": None,
            },
        )
        NODE_BOOTSTRAP_TOTAL.labels(result="installer_completed").inc()
        logger_node.info(
            "node installer reported bootstrap complete",
            node_id=str(node.id),
            name=node.name,
        )
        return now

    @staticmethod
    def _mint_bootstrap_token() -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        return raw, token_hash

    @staticmethod
    def _bootstrap_token_expires_at() -> datetime:
        ttl = get_settings().k3s.bootstrap_token_ttl_sec
        return datetime.now(timezone.utc) + timedelta(seconds=ttl)

    @staticmethod
    def _render_install_command(raw_token: str) -> str:
        base = get_settings().k3s.public_base_url
        if not base:
            return (
                "# Set CONTROL_API_PUBLIC_URL in control-api env to render a real one-liner.\n"
                f"# token={raw_token}"
            )
        return (
            f"curl -fsSL '{base}/api/v1/agent/install.sh?token={raw_token}' "
            f"| sudo bash"
        )


async def get_vpn_node_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> VpnNodeService:
    return VpnNodeService(session)
