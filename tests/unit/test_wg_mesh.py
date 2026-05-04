from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.config import WgMeshConfig
from services.wg.allocator import allocate_next_ip
from services.wg.exceptions import WgMeshAddressPoolExhaustedError
from services.wg.schemas import WgRegisterIn
from services.wg.service import WgMeshService


class TestAllocator:
    def test_allocates_next_free(self):
        ip = allocate_next_ip(cidr="10.10.0.0/29", used={"10.10.0.2", "10.10.0.3"})
        assert ip == "10.10.0.4"

    def test_skips_reserved(self):
        ip = allocate_next_ip(cidr="10.10.0.0/29", used=set(), reserved=2)
        assert ip == "10.10.0.3"

    def test_raises_when_exhausted(self):
        used = {f"10.10.0.{i}" for i in range(1, 8)}
        with pytest.raises(WgMeshAddressPoolExhaustedError):
            allocate_next_ip(cidr="10.10.0.0/29", used=used)


@pytest.mark.asyncio
class TestWgMeshService:
    def _config(self) -> WgMeshConfig:
        return WgMeshConfig(enabled=True, mesh_cidr="10.10.0.0/24", listen_port=51820)

    def _node(self, **overrides):
        n = MagicMock()
        n.id = overrides.get("id", uuid4())
        n.name = overrides.get("name", "n")
        n.role = overrides.get("role", "backend")
        n.is_enabled = overrides.get("is_enabled", True)
        n.is_draining = overrides.get("is_draining", False)
        n.zone = overrides.get("zone", "europe")
        n.region = overrides.get("region", "fi")
        n.reality_ip = overrides.get("reality_ip", "1.1.1.1")
        n.public_domain = overrides.get("public_domain", "")
        n.internal_wg_ip = overrides.get("internal_wg_ip", "")
        n.wg_public_key = overrides.get("wg_public_key")
        n.wg_listen_port = overrides.get("wg_listen_port")
        return n

    async def test_register_assigns_first_address(self):
        node = self._node(name="hel", reality_ip="1.1.1.1")
        node_repo = MagicMock()
        node_repo.list = AsyncMock(return_value=[node])
        node_repo.update_by_id = AsyncMock()
        svc = WgMeshService(session=MagicMock(), config=self._config())
        svc.node_repo = node_repo

        out = await svc.register(
            node=node,
            payload=WgRegisterIn(public_key="A" * 44, listen_port=51820),
        )
        assert out.address == "10.10.0.2"
        assert out.peers == []
        node_repo.update_by_id.assert_awaited_once()

    async def test_register_returns_existing_address(self):
        node = self._node(name="hel", internal_wg_ip="10.10.0.5")
        node_repo = MagicMock()
        node_repo.list = AsyncMock(return_value=[node])
        node_repo.update_by_id = AsyncMock()
        svc = WgMeshService(session=MagicMock(), config=self._config())
        svc.node_repo = node_repo

        out = await svc.register(
            node=node,
            payload=WgRegisterIn(public_key="B" * 44, listen_port=51820),
        )
        assert out.address == "10.10.0.5"

    async def test_register_skips_used_addresses(self):
        peer = self._node(name="par", internal_wg_ip="10.10.0.2", wg_public_key="X" * 44)
        node = self._node(name="hel")
        node_repo = MagicMock()
        node_repo.list = AsyncMock(return_value=[peer, node])
        node_repo.update_by_id = AsyncMock()
        svc = WgMeshService(session=MagicMock(), config=self._config())
        svc.node_repo = node_repo

        out = await svc.register(
            node=node,
            payload=WgRegisterIn(public_key="C" * 44, listen_port=51820),
        )
        assert out.address == "10.10.0.3"

    async def test_register_returns_peers_with_keys(self):
        peer_a = self._node(name="par", internal_wg_ip="10.10.0.2", wg_public_key="A" * 44, reality_ip="2.2.2.2")
        peer_no_key = self._node(name="rix", internal_wg_ip="10.10.0.4", wg_public_key=None, reality_ip="3.3.3.3")
        node = self._node(name="hel")
        node_repo = MagicMock()
        node_repo.list = AsyncMock(return_value=[peer_a, peer_no_key, node])
        node_repo.update_by_id = AsyncMock()
        svc = WgMeshService(session=MagicMock(), config=self._config())
        svc.node_repo = node_repo

        out = await svc.register(
            node=node,
            payload=WgRegisterIn(public_key="Z" * 44, listen_port=51820),
        )
        assert [p.name for p in out.peers] == ["par"]
        assert out.peers[0].endpoint == "2.2.2.2"
