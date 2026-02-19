import hashlib
import logging
import secrets
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode
from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.nodes.schemas import (
    NodeAgentStateUpdate,
    NodeHeartbeatIn,
    NodeAgentInitialOut,
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

    async def initial(self, *, source_ip: str) -> NodeAgentInitialOut:
        """
        Initial node identity bootstrap.

        - identity source: internal_wg_ip (source_ip)
        - idempotent
        - rotates auth token on every call
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
        else:
            update_schema = VpnNodeUpdate(
                auth_token_hash=token_hash
            )
            await self.vpn_node_repository.update_by_id(
                node.id,
                update_schema.model_dump(exclude_unset=True)
            )
            NODE_BOOTSTRAP_TOTAL.labels(result="rotated").inc()

        return NodeAgentInitialOut(
            node_id=str(node.id),
            node_auth_token=raw_token,
        )

    async def handle_heartbeat(
            self,
            node: VpnNode,
            payload: NodeHeartbeatIn,
    ) -> None:
        now = datetime.now(timezone.utc)

        state = NodeAgentStateUpdate(
            agent_version=payload.agent_version,
            is_healthy=payload.is_healthy,
            last_seen_at=now,
            details=payload.details.model_dump(),
        )
        await self.node_agent_state_repository.upsert(
            {
                "node_id": node.id,
                **state.model_dump(exclude_unset=True),
            }
        )
        if not payload.is_healthy and not node.is_draining:
            await self.vpn_node_repository.update_by_id(
                node.id,
                {"is_draining": True},
            )
            logger_node.info(
                "node set to draining due to unhealthy heartbeat",
                node_id=str(node.id),
            )


async def get_vpn_node_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> VpnNodeService:
    return VpnNodeService(session)
