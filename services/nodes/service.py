import hashlib
import logging
import secrets
from datetime import datetime, timezone
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
    NodeAgentStateCreate,
    NodeAgentStateUpdate,
    NodeHeartbeatIn,
    NodeAgentInitialOut,
    NodeSyncDetails,
    NodeSyncReportIn,
    VpnNodeUpdate,
    VpnNodeCreate,
    NodeRole,
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
        self.sync_report_debounce_sec = max(0, int(get_settings().node_agent.sync_report_debounce_sec))

    async def initial(
            self,
            *,
            source_ip: str,
            agent_instance_id: UUID | None = None,
    ) -> NodeAgentInitialOut:
        """
        Initial node identity bootstrap.

        - identity source: internal_wg_ip (source_ip)
        - idempotent
        - when X-Agent-Instance-ID is provided, token is managed per agent instance
        - legacy mode (no X-Agent-Instance-ID) keeps per-node token behavior
        """

        node = await self.vpn_node_repository.get_by_internal_ip(source_ip)

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        if node is None:
            create_schema = VpnNodeCreate(
                name=f"node-{source_ip.replace('.', '-')}",
                role=NodeRole.backend,
                region="unknown",
                public_domain="",
                internal_wg_ip=source_ip,
                xray_api_port=10085,
                agent_port=9000,
                auth_token_hash=token_hash,
            )

            node = await self.vpn_node_repository.create(
                create_schema.model_dump()
            )
            NODE_BOOTSTRAP_TOTAL.labels(result="created").inc()
        elif agent_instance_id is None:
            update_schema = VpnNodeUpdate(
                auth_token_hash=token_hash
            )
            await self.vpn_node_repository.update_by_id(
                node.id,
                update_schema.model_dump(exclude_unset=True)
            )
            NODE_BOOTSTRAP_TOTAL.labels(result="rotated").inc()

        if agent_instance_id is not None:
            await self.node_agent_identity_repository.upsert_token(
                node_id=node.id,
                agent_instance_id=agent_instance_id,
                token_hash=token_hash,
            )
            NODE_BOOTSTRAP_TOTAL.labels(result="identity_issued").inc()

        return NodeAgentInitialOut(
            node_id=str(node.id),
            node_auth_token=raw_token,
            agent_instance_id=str(agent_instance_id) if agent_instance_id else None,
        )

    async def handle_heartbeat(
            self,
            node: VpnNode,
            payload: NodeHeartbeatIn,
    ) -> None:
        now = datetime.now(timezone.utc)
        details = NodeAgentDetails(
            runtime=payload.details.runtime,
            stats=payload.details.stats,
        )
        state = NodeAgentStateCreate(
            node_id=node.id,
            agent_version=payload.agent_version,
            is_healthy=payload.is_healthy,
            last_seen_at=now,
            last_sync_at=None,
            details=details.model_dump(mode="json", exclude_none=True),
        )
        await self.node_agent_state_repository.upsert(state.model_dump(exclude_none=True))
        if not payload.is_healthy and not node.is_draining:
            await self.vpn_node_repository.update_by_id(
                node.id,
                {"is_draining": True},
            )
            logger_node.info(
                "node set to draining due to unhealthy heartbeat",
                node_id=str(node.id),
            )

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
        existing_synced_count = existing_details.sync.synced_count if existing_details.sync else None
        if existing_synced_count != payload.synced_count:
            return False
        return True

    @staticmethod
    def _to_utc_or_none(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


async def get_vpn_node_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> VpnNodeService:
    return VpnNodeService(session)
