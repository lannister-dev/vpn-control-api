from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from services.config import WgMeshConfig
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.wg.schemas import WgPeerOut
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("wg-mesh-service"))

# Roles that should peer with each other across the wg-mesh.
# Same-role peerings are dropped: backends do not carry traffic to other
# backends, and entries do not need a tunnel to other entries. Eliminating
# these reduces handshake overhead and avoids provider-side UDP filtering
# that some hosters apply between VPS in the same AS.
_PEER_ROLES: dict[str, set[str]] = {
    "backend": {"entry", "whitelist_entry"},
    "entry": {"backend"},
    "whitelist_entry": {"backend"},
}


class WgMeshService:
    def __init__(self, session: AsyncSession, *, config: WgMeshConfig):
        self.session = session
        self.config = config
        self.node_repo = VpnNodeRepository(session)

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
        self, *, all_nodes: Sequence[VpnNode], exclude_id, self_role: str | None = None,
    ) -> list[WgPeerOut]:
        allowed_roles = _PEER_ROLES.get(self_role or "") if self_role else None
        peers: list[WgPeerOut] = []
        for n in all_nodes:
            if n.id == exclude_id:
                continue
            if allowed_roles is not None and (n.role or "") not in allowed_roles:
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
