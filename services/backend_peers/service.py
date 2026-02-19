from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.backend_peers.model import BackendPeer
from services.backend_peers.repository import BackendPeerRepository
from services.backend_peers.schemas import (
    BackendPeerAppliedState,
    BackendPeerGatewayItemOut,
    BackendPeerGatewayPageOut,
    BackendPeerOut,
    BackendPeerPageItemOut,
    BackendPeerPageOut,
    BackendPeerReportIn,
    BackendPeerReportStatus,
    BackendPeerStatus,
    BackendPeerUpsertIn,
)
from services.nodes.models import VpnNode
from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.nodes.schemas import NodeRole
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import NODE_BACKEND_PEER_REPORT_TOTAL


class BackendPeerService:
    def __init__(self, session: AsyncSession):
        self.peer_repository = BackendPeerRepository(session)
        self.node_repository = VpnNodeRepository(session)

    async def upsert(self, payload: BackendPeerUpsertIn) -> BackendPeerOut:
        backend = await self.node_repository.get_by_id(payload.backend_node_id)
        if not backend:
            raise HTTPException(status_code=404, detail="Backend node not found")
        self._assert_backend_node(backend)

        gateway = await self.node_repository.get_by_id(payload.gateway_node_id)
        if not gateway:
            raise HTTPException(status_code=404, detail="Gateway node not found")
        self._assert_gateway_node(gateway)

        peer = await self.peer_repository.upsert_set_pending(
            backend_node_id=payload.backend_node_id,
            gateway_node_id=payload.gateway_node_id,
            status=payload.status,
            internal_uuid=str(payload.internal_uuid) if payload.internal_uuid else None,
        )
        return BackendPeerOut.model_validate(peer)

    async def ensure_active_pair(
            self,
            *,
            backend_node_id: UUID,
            gateway_node_id: UUID,
    ) -> BackendPeerOut:
        backend = await self.node_repository.get_by_id(backend_node_id)
        if not backend:
            raise HTTPException(status_code=404, detail="Backend node not found")
        self._assert_backend_node(backend)

        gateway = await self.node_repository.get_by_id(gateway_node_id)
        if not gateway:
            raise HTTPException(status_code=404, detail="Gateway node not found")
        self._assert_gateway_node(gateway)

        peer = await self.peer_repository.ensure_active_pair(
            backend_node_id=backend_node_id,
            gateway_node_id=gateway_node_id,
        )
        return BackendPeerOut.model_validate(peer)

    async def list_peers(
            self,
            *,
            backend_node_id: UUID | None = None,
            gateway_node_id: UUID | None = None,
            limit: int = 200,
    ) -> list[BackendPeerOut]:
        rows = await self.peer_repository.list_active(
            backend_node_id=backend_node_id,
            gateway_node_id=gateway_node_id,
            limit=limit,
        )
        return [BackendPeerOut.model_validate(row) for row in rows]

    @staticmethod
    def _assert_backend_node(node: VpnNode) -> None:
        role = getattr(node, "role", NodeRole.backend.value)
        if role != NodeRole.backend.value:
            raise HTTPException(status_code=409, detail="Node role must be backend")

    @staticmethod
    def _assert_gateway_node(node: VpnNode) -> None:
        role = getattr(node, "role", NodeRole.gateway.value)
        if role != NodeRole.gateway.value:
            raise HTTPException(status_code=409, detail="Node role must be gateway")
        if not getattr(node, "public_domain", "").strip():
            raise HTTPException(status_code=409, detail="Gateway node must have public_domain")
        if not getattr(node, "is_active", True) or not getattr(node, "is_enabled", True):
            raise HTTPException(status_code=409, detail="Gateway node is not active")
        if getattr(node, "is_draining", False):
            raise HTTPException(status_code=409, detail="Gateway node is draining")


class BackendPeerAgentService:
    def __init__(self, session: AsyncSession):
        self.peer_repository = BackendPeerRepository(session)
        self.node_agent_state_repository = NodeAgentStateRepository(session)

    async def get_page_for_backend(
            self,
            *,
            node: VpnNode,
            cursor: str | None,
            limit: int,
    ) -> BackendPeerPageOut:
        if getattr(node, "role", None) != NodeRole.backend.value:
            raise HTTPException(status_code=403, detail="Node role must be backend")

        parsed: tuple[int, UUID] | None = None
        if cursor:
            try:
                op_s, pid_s = cursor.split(":", 1)
                parsed = (int(op_s), UUID(pid_s))
            except Exception as exc:
                raise ValueError(f"Invalid cursor format: {cursor!r}") from exc

        rows = await self.peer_repository.list_for_backend_page(
            backend_node_id=node.id,
            cursor=parsed,
            limit=limit,
        )
        items = self._build_items(rows)
        next_cursor = None
        if items:
            last = items[-1]
            next_cursor = f"{last.op_version}:{last.id}"
        return BackendPeerPageOut(items=items, next_cursor=next_cursor)

    async def report_for_backend(
            self,
            *,
            node: VpnNode,
            peer_id: UUID,
            payload: BackendPeerReportIn,
    ) -> BackendPeerReportStatus:
        if getattr(node, "role", None) != NodeRole.backend.value:
            raise HTTPException(status_code=403, detail="Node role must be backend")
        peer = await self.peer_repository.get_by_id(peer_id)
        if not peer:
            raise HTTPException(status_code=404, detail="Backend peer not found")

        if peer.backend_node_id != node.id:
            raise HTTPException(status_code=403, detail="Backend peer does not belong to this node")

        if payload.op_version != peer.op_version:
            NODE_BACKEND_PEER_REPORT_TOTAL.labels(status="skipped_stale").inc()
            return "skipped_stale"

        if (
                peer.applied_version == payload.op_version
                and peer.applied_state == payload.applied_state
                and (peer.last_error or None) == (payload.last_error or None)
        ):
            NODE_BACKEND_PEER_REPORT_TOTAL.labels(status="skipped_idempotent").inc()
            return "skipped_idempotent"

        now = datetime.now(timezone.utc)
        applied_state_value: str = payload.applied_state
        updated_rows = await self.peer_repository.apply_backend_report(
            peer_id=peer.id,
            backend_node_id=node.id,
            expected_op_version=payload.op_version,
            applied_state=applied_state_value,
            applied_version=payload.op_version,
            last_error=payload.last_error,
            updated_at=now,
        )
        if updated_rows == 0:
            NODE_BACKEND_PEER_REPORT_TOTAL.labels(status="skipped_stale").inc()
            return "skipped_stale"

        if payload.applied_state == BackendPeerAppliedState.applied:
            await self.node_agent_state_repository.touch_last_sync(node_id=node.id, at=now)
            NODE_BACKEND_PEER_REPORT_TOTAL.labels(status="applied").inc()
            return "applied"
        if payload.applied_state == BackendPeerAppliedState.error:
            NODE_BACKEND_PEER_REPORT_TOTAL.labels(status="error").inc()
            return "error"

        NODE_BACKEND_PEER_REPORT_TOTAL.labels(status="pending").inc()
        return "pending"

    @staticmethod
    def _build_items(rows: Sequence[tuple[BackendPeer, VpnNode]]) -> list[BackendPeerPageItemOut]:
        out: list[BackendPeerPageItemOut] = []
        for peer, gateway_node in rows:
            status = BackendPeerStatus(peer.status)
            if not getattr(gateway_node, "is_enabled", True) or getattr(gateway_node, "is_draining", False):
                status = BackendPeerStatus.inactive
            if getattr(gateway_node, "role", NodeRole.gateway.value) != NodeRole.gateway.value:
                status = BackendPeerStatus.inactive
            out.append(
                BackendPeerPageItemOut(
                    id=peer.id,
                    backend_node_id=peer.backend_node_id,
                    gateway_node_id=peer.gateway_node_id,
                    internal_uuid=peer.internal_uuid,
                    status=status,
                    applied_state=BackendPeerAppliedState(peer.applied_state),
                    op_version=peer.op_version,
                    applied_version=peer.applied_version,
                    last_error=peer.last_error,
                    gateway_public_domain=gateway_node.public_domain,
                )
            )
        return out


class BackendPeerGatewayAgentService:
    def __init__(self, session: AsyncSession):
        self.peer_repository = BackendPeerRepository(session)

    async def get_page_for_gateway(
            self,
            *,
            node: VpnNode,
            cursor: str | None,
            limit: int,
    ) -> BackendPeerGatewayPageOut:
        if getattr(node, "role", None) != NodeRole.gateway.value:
            raise HTTPException(status_code=403, detail="Node role must be gateway")

        parsed: tuple[int, UUID] | None = None
        if cursor:
            try:
                op_s, pid_s = cursor.split(":", 1)
                parsed = (int(op_s), UUID(pid_s))
            except Exception as exc:
                raise ValueError(f"Invalid cursor format: {cursor!r}") from exc

        rows = await self.peer_repository.list_for_gateway_page(
            gateway_node_id=node.id,
            cursor=parsed,
            limit=limit,
        )
        items = self._build_items(rows)
        next_cursor = None
        if items:
            last = items[-1]
            next_cursor = f"{last.op_version}:{last.id}"
        return BackendPeerGatewayPageOut(items=items, next_cursor=next_cursor)

    @staticmethod
    def _build_items(rows: Sequence[tuple[BackendPeer, VpnNode]]) -> list[BackendPeerGatewayItemOut]:
        out: list[BackendPeerGatewayItemOut] = []
        for peer, backend_node in rows:
            status = BackendPeerStatus(peer.status)
            if not getattr(backend_node, "is_enabled", True) or getattr(backend_node, "is_draining", False):
                status = BackendPeerStatus.inactive
            if getattr(backend_node, "role", NodeRole.backend.value) != NodeRole.backend.value:
                status = BackendPeerStatus.inactive
            out.append(
                BackendPeerGatewayItemOut(
                    id=peer.id,
                    backend_node_id=peer.backend_node_id,
                    internal_uuid=peer.internal_uuid,
                    status=status,
                    applied_state=BackendPeerAppliedState(peer.applied_state),
                    op_version=peer.op_version,
                    applied_version=peer.applied_version,
                    last_error=peer.last_error,
                    backend_internal_wg_ip=backend_node.internal_wg_ip,
                    backend_xray_api_port=backend_node.xray_api_port,
                )
            )
        return out


def get_backend_peer_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> BackendPeerService:
    return BackendPeerService(session)


def get_backend_peer_agent_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> BackendPeerAgentService:
    return BackendPeerAgentService(session)


def get_backend_peer_gateway_agent_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> BackendPeerGatewayAgentService:
    return BackendPeerGatewayAgentService(session)
