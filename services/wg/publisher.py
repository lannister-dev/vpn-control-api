from __future__ import annotations

import logging
from uuid import UUID

from services.config import NatsConfig, WgMeshConfig, get_settings
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import VpnNodeUpdate
from services.wg.allocator import allocate_next_ip
from services.wg.constants import KV_KEY_PREFIX, KV_PEERS_BUCKET, KV_PUBKEYS_BUCKET
from services.wg.schemas import WgPubkeyKvPayload
from services.wg.service import WgMeshService
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("wg-mesh-publisher"))

PUBLISHER_TICK_SEC_DEFAULT = 30
PUBLISHER_IDLE_WHEN_DISABLED_SEC = 60


class WgMeshPeerPublisher(Reconciler):
    name = "wg_mesh_publisher"

    def __init__(
        self,
        *,
        wg_config: WgMeshConfig | None = None,
        nats_config: NatsConfig | None = None,
        nats_client: NatsClient | None = None,
        tick_sec: int = PUBLISHER_TICK_SEC_DEFAULT,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        settings = get_settings()
        self._cfg = wg_config or settings.wg_mesh
        self._nats_cfg = nats_config or settings.nats
        super().__init__(
            interval_sec=max(5, int(tick_sec)),
            enabled=bool(self._cfg.enabled),
            tick_lock=tick_lock,
        )
        self._session_maker = AsyncDatabase.get_session_maker()
        self._nats: NatsClient | None = nats_client
        self._owns_nats = nats_client is None
        self._last_signatures: dict[UUID, str] = {}

    async def stop(self) -> None:
        await super().stop()
        if self._owns_nats and self._nats is not None:
            await self._nats.close()
            self._nats = None

    async def _ensure_nats(self) -> NatsClient:
        if self._nats is None:
            self._nats = NatsClient(self._nats_cfg)
        if not self._nats.is_connected:
            await self._nats.connect()
            await self._nats.ensure_kv_bucket(name=KV_PEERS_BUCKET, history=1)
            await self._nats.ensure_kv_bucket(name=KV_PUBKEYS_BUCKET, history=1)
        return self._nats

    async def tick(self) -> None:
        nats = await self._ensure_nats()
        async with self._session_maker() as session:
            await self._sync_pubkeys_from_kv(session=session, nats=nats)
            if session.has_pending_writes():
                await session.commit()
            service = WgMeshService(session, config=self._cfg)
            nodes = await VpnNodeRepository(session).list()
            published = 0
            for node in nodes:
                if not node.wg_public_key:
                    continue
                if not (node.internal_wg_ip or "").strip():
                    continue
                peers = service._build_peers(
                    all_nodes=nodes, exclude_id=node.id, self_role=node.role,
                )
                payload = {
                    "node_id": str(node.id),
                    "address": node.internal_wg_ip,
                    "listen_port": int(node.wg_listen_port or self._cfg.listen_port),
                    "peers": [p.model_dump(mode="json") for p in peers],
                }
                signature = self._signature_for(payload)
                if self._last_signatures.get(node.id) == signature:
                    continue
                await nats.kv_put(
                    bucket=KV_PEERS_BUCKET,
                    key=f"{KV_KEY_PREFIX}{node.id}",
                    payload=payload,
                )
                self._last_signatures[node.id] = signature
                published += 1
            if published:
                logger.info("wg_mesh_peers_published", nodes=published, total=len(nodes))

    async def _sync_pubkeys_from_kv(self, *, session, nats: NatsClient) -> None:
        entries = await nats.kv_list_all(bucket=KV_PUBKEYS_BUCKET)
        if not entries:
            return
        repo = VpnNodeRepository(session)
        nodes_by_id = {str(n.id): n for n in await repo.list()}
        synced_count = 0
        for key, raw in entries.items():
            try:
                payload = WgPubkeyKvPayload.model_validate_json(raw)
            except Exception as exc:
                logger.warning("wg_pubkey_kv_invalid_payload", key=key, err=str(exc))
                continue
            node = nodes_by_id.get(str(payload.node_id))
            if node is None:
                logger.warning("wg_pubkey_kv_unknown_node", node_id=str(payload.node_id))
                continue
            current_used = {
                n.internal_wg_ip for n in nodes_by_id.values()
                if n.id != node.id and (n.internal_wg_ip or "").strip()
            }
            address = (node.internal_wg_ip or "").strip()
            if not address:
                address = allocate_next_ip(cidr=self._cfg.mesh_cidr, used=current_used)
            if (
                node.wg_public_key == payload.public_key
                and node.wg_listen_port == payload.listen_port
                and node.internal_wg_ip == address
            ):
                continue
            update = VpnNodeUpdate(
                wg_public_key=payload.public_key,
                wg_listen_port=payload.listen_port,
                internal_wg_ip=address,
            )
            await repo.update_by_id(node.id, update.model_dump(exclude_unset=True))
            node.wg_public_key = payload.public_key
            node.wg_listen_port = payload.listen_port
            node.internal_wg_ip = address
            synced_count += 1
        if synced_count:
            logger.info("wg_pubkey_kv_synced", count=synced_count)

    @staticmethod
    def _signature_for(payload: dict) -> str:
        import hashlib
        import json

        normalized = {
            "address": payload["address"],
            "listen_port": payload["listen_port"],
            "peers": sorted(
                [(p["public_key"], p["address"]) for p in payload["peers"]]
            ),
        }
        return hashlib.sha256(
            json.dumps(normalized, sort_keys=True).encode()
        ).hexdigest()
