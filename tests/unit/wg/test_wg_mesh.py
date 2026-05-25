from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.config import WgMeshConfig
from services.wg.allocator import allocate_next_ip
from services.wg.exceptions import WgMeshAddressPoolExhaustedError


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


def _node(**overrides):
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
    n.auth_token_hash = overrides.get("auth_token_hash", "")
    return n


@pytest.mark.asyncio
class TestPubkeySyncFromKv:
    def _publisher(self):
        from services.wg.publisher import WgMeshPeerPublisher

        cfg = WgMeshConfig(enabled=True, mesh_cidr="10.10.0.0/24", listen_port=51820)
        nats_cfg = MagicMock()
        return WgMeshPeerPublisher(wg_config=cfg, nats_config=nats_cfg)

    def _kv_payload(self, *, node_id, public_key, listen_port=51820) -> bytes:
        return json.dumps({
            "node_id": str(node_id),
            "public_key": public_key,
            "listen_port": listen_port,
        }).encode()

    async def test_syncs_pubkey(self, monkeypatch):
        node_id = uuid4()
        node = _node(id=node_id)
        repo_list = AsyncMock(return_value=[node])
        update_by_id = AsyncMock()

        nats = MagicMock()
        nats.kv_list_all = AsyncMock(return_value={
            f"node.{node_id}": self._kv_payload(
                node_id=node_id, public_key="P" * 44,
            ),
        })

        publisher = self._publisher()
        with monkeypatch.context() as m:
            m.setattr("services.wg.publisher.VpnNodeRepository",
                      lambda session: MagicMock(list=repo_list, update_by_id=update_by_id))
            await publisher._sync_pubkeys_from_kv(session=MagicMock(), nats=nats)

        update_by_id.assert_awaited_once()
        kwargs = update_by_id.await_args.args[1]
        assert kwargs["wg_public_key"] == "P" * 44
        assert kwargs["internal_wg_ip"] == "10.10.0.2"

    async def test_skips_unknown_node(self, monkeypatch):
        node = _node()
        repo_list = AsyncMock(return_value=[node])
        update_by_id = AsyncMock()

        nats = MagicMock()
        nats.kv_list_all = AsyncMock(return_value={
            "node.deadbeef-0000-0000-0000-000000000000": self._kv_payload(
                node_id="deadbeef-0000-0000-0000-000000000000",
                public_key="Z" * 44,
            ),
        })

        publisher = self._publisher()
        with monkeypatch.context() as m:
            m.setattr("services.wg.publisher.VpnNodeRepository",
                      lambda session: MagicMock(list=repo_list, update_by_id=update_by_id))
            await publisher._sync_pubkeys_from_kv(session=MagicMock(), nats=nats)

        update_by_id.assert_not_awaited()

    async def test_no_op_when_already_synced(self, monkeypatch):
        node_id = uuid4()
        pubkey = "K" * 44
        node = _node(
            id=node_id,
            wg_public_key=pubkey,
            wg_listen_port=51820,
            internal_wg_ip="10.10.0.5",
        )
        repo_list = AsyncMock(return_value=[node])
        update_by_id = AsyncMock()

        nats = MagicMock()
        nats.kv_list_all = AsyncMock(return_value={
            f"node.{node_id}": self._kv_payload(
                node_id=node_id, public_key=pubkey,
            ),
        })

        publisher = self._publisher()
        with monkeypatch.context() as m:
            m.setattr("services.wg.publisher.VpnNodeRepository",
                      lambda session: MagicMock(list=repo_list, update_by_id=update_by_id))
            await publisher._sync_pubkeys_from_kv(session=MagicMock(), nats=nats)

        update_by_id.assert_not_awaited()
