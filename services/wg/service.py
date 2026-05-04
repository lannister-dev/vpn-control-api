from __future__ import annotations

import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import WgMeshConfig, get_settings
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import VpnNodeUpdate
from services.wg.allocator import allocate_next_ip
from services.wg.exceptions import WgMeshUnknownNodeError
from services.wg.schemas import WgPeerOut, WgRegisterIn, WgRegisterOut
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("wg-mesh-service"))


class WgMeshService:
    def __init__(self, session: AsyncSession, *, config: WgMeshConfig):
        self.session = session
        self.config = config
        self.node_repo = VpnNodeRepository(session)

    async def register(self, *, node: VpnNode, payload: WgRegisterIn) -> WgRegisterOut:
        all_nodes = await self.node_repo.list()
        used = self._collect_assigned_ips(all_nodes, exclude_id=node.id)
        address = self._existing_or_new_address(node=node, used=used)

        update = VpnNodeUpdate(
            wg_public_key=payload.public_key,
            wg_listen_port=payload.listen_port,
            internal_wg_ip=address,
        )
        await self.node_repo.update_by_id(
            node.id, update.model_dump(exclude_unset=True),
        )
        node.wg_public_key = payload.public_key
        node.wg_listen_port = payload.listen_port
        node.internal_wg_ip = address

        peers = self._build_peers(all_nodes=all_nodes, exclude_id=node.id)
        return WgRegisterOut(node_id=node.id, address=address, peers=peers)

    async def build_peers_for_node(self, node_id) -> list[WgPeerOut]:
        node = await self.node_repo.get_by_id(node_id)
        if node is None:
            raise WgMeshUnknownNodeError(str(node_id))
        all_nodes = await self.node_repo.list()
        return self._build_peers(all_nodes=all_nodes, exclude_id=node.id)

    def _collect_assigned_ips(
        self, nodes: list[VpnNode], *, exclude_id,
    ) -> set[str]:
        used: set[str] = set()
        for n in nodes:
            if n.id == exclude_id:
                continue
            ip = self._mesh_ip_or_none(n)
            if ip is not None:
                used.add(ip)
        return used

    def _existing_or_new_address(
        self, *, node: VpnNode, used: set[str],
    ) -> str:
        current = self._mesh_ip_or_none(node)
        if current is not None:
            return current
        return allocate_next_ip(cidr=self.config.mesh_cidr, used=used)

    def _mesh_ip_or_none(self, node: VpnNode) -> str | None:
        from ipaddress import IPv4Address, IPv4Network

        ip = (node.internal_wg_ip or "").strip()
        if not ip:
            return None
        try:
            addr = IPv4Address(ip)
        except ValueError:
            return None
        if addr not in IPv4Network(self.config.mesh_cidr, strict=False):
            return None
        return ip

    def _build_peers(
        self, *, all_nodes: list[VpnNode], exclude_id,
    ) -> list[WgPeerOut]:
        peers: list[WgPeerOut] = []
        for n in all_nodes:
            if n.id == exclude_id:
                continue
            if not n.wg_public_key:
                continue
            mesh_ip = self._mesh_ip_or_none(n)
            if mesh_ip is None:
                continue
            endpoint = (n.reality_ip or n.public_domain or "").strip()
            if not endpoint:
                continue
            peers.append(
                WgPeerOut(
                    node_id=n.id,
                    name=n.name,
                    public_key=n.wg_public_key,
                    endpoint=endpoint,
                    listen_port=int(n.wg_listen_port or self.config.listen_port),
                    address=mesh_ip,
                )
            )
        return sorted(peers, key=lambda p: p.name)


def get_wg_mesh_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> WgMeshService:
    return WgMeshService(session, config=get_settings().wg_mesh)
