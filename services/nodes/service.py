import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode
from services.nodes.repository import (
    NodeAgentIdentityRepository,
    NodeAgentStateRepository,
    VpnNodeRepository,
)
from services.config import get_settings
from services.nodes.schemas import (
    NodeAgentDetails,
    NodeHeartbeatMeta,
    NodeAgentStateCreate,
    NodeAgentStateUpdate,
    NodeHeartbeatIn,
    NodeAgentInitialOut,
    NodeSyncDetails,
    NodeSyncReportIn,
    VpnNodeCreate,
)
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import (
    NODE_BOOTSTRAP_TOTAL,
)
from shared.utils.logger import StructuredLogger

logger_node = StructuredLogger(logging.getLogger("node-service"))


class NodeBootstrapConflictError(ValueError):
    pass


class VpnNodeService:
    _HEARTBEAT_DETAILS_KEY = "heartbeat"
    _DRAIN_REASON_UNHEALTHY_HEARTBEAT = "unhealthy_heartbeat"

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
        node = await self.vpn_node_repository.get_by_node_key(normalized_node_key)
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

    async def handle_heartbeat(
            self,
            node: VpnNode,
            payload: NodeHeartbeatIn,
    ) -> None:
        now = datetime.now(timezone.utc)
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
            is_healthy=payload.is_healthy,
        )
        should_drain = (
            not payload.is_healthy
            and not node.is_draining
            and heartbeat_meta.consecutive_unhealthy >= self.heartbeat_unhealthy_drain_threshold
        )
        if should_drain:
            await self.vpn_node_repository.update_by_id(
                node.id,
                {"is_draining": True},
            )
            node.is_draining = True
            heartbeat_meta.drain_reason = self._DRAIN_REASON_UNHEALTHY_HEARTBEAT
            heartbeat_meta.drained_at = now
            logger_node.info(
                "node set to draining after unhealthy heartbeat threshold",
                node_id=str(node.id),
                threshold=self.heartbeat_unhealthy_drain_threshold,
                consecutive_unhealthy=heartbeat_meta.consecutive_unhealthy,
            )
        should_undrain = (
            payload.is_healthy
            and node.is_draining
            and node.is_active
            and node.is_enabled
            and heartbeat_meta.drain_reason == self._DRAIN_REASON_UNHEALTHY_HEARTBEAT
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
            logger_node.info(
                "node restored from draining after healthy heartbeat threshold",
                node_id=str(node.id),
                threshold=self.heartbeat_healthy_undrain_threshold,
                consecutive_healthy=heartbeat_meta.consecutive_healthy,
            )
        details_data = details.model_dump(mode="json", exclude_none=True)
        details_data[self._HEARTBEAT_DETAILS_KEY] = heartbeat_meta.model_dump(
            mode="json",
            exclude_none=True,
        )
        state = NodeAgentStateCreate(
            node_id=node.id,
            agent_version=payload.agent_version,
            is_healthy=payload.is_healthy,
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

    @classmethod
    def _next_heartbeat_meta(
            cls,
            *,
            base_details: dict[str, object],
            is_healthy: bool,
    ) -> NodeHeartbeatMeta:
        heartbeat_raw = base_details.get(cls._HEARTBEAT_DETAILS_KEY)
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


async def get_vpn_node_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> VpnNodeService:
    return VpnNodeService(session)
