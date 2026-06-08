from __future__ import annotations

import hashlib
import logging
import time
from uuid import UUID

from pydantic import ValidationError

from services.nodes.models import VpnNode
from services.routing.entry.constants import KV_STATS_BUCKET
from services.routing.entry.schemas import EntryRoutingStatsKv
from shared.utils.logger import StructuredLogger
from shared.utils.node_display import effective_zone

logger = StructuredLogger(logging.getLogger("balancer.entry"))


class EntryBalancer:
    def __init__(self, *, nats=None, settings):
        self._nats = nats
        self._settings = settings

    def bucket(self) -> int | None:
        bucket_sec = self._settings.entry_relay.user_entry_bucket_seconds
        if bucket_sec <= 0:
            return None
        return int(time.time()) // bucket_sec

    async def live_entry_loads(self) -> dict[UUID, int]:
        if self._nats is None:
            return {}
        try:
            entries = await self._nats.kv_list_all(bucket=KV_STATS_BUCKET)
        except Exception:
            logger.exception("live_entry_loads_fetch_failed")
            return {}
        loads: dict[UUID, int] = {}
        for raw in entries.values():
            try:
                stats = EntryRoutingStatsKv.model_validate_json(raw)
            except ValidationError:
                continue
            if stats.node_id is not None:
                loads[stats.node_id] = loads.get(stats.node_id, 0) + stats.total
        return loads

    def select_entry_for_backend(
            self,
            *,
            backend_node: VpnNode,
            current_entry: VpnNode | None,
            user_id,
            entries_by_zone: dict[str, list[VpnNode]],
            entry_loads: dict | None = None,
    ) -> VpnNode | None:
        zone = effective_zone(
            explicit_zone=backend_node.zone,
            region=backend_node.region,
        )
        candidates = list(entries_by_zone.get(zone) or [])
        if self._is_entry_usable(current_entry) and current_entry not in candidates:
            candidates.append(current_entry)
        required_role = current_entry.role if current_entry is not None else None
        if required_role:
            candidates = [e for e in candidates if e.role == required_role]
        candidates = [e for e in candidates if self._is_entry_usable(e)]
        if not candidates:
            return current_entry if self._is_entry_usable(current_entry) else None

        loads = entry_loads or {}
        bucket = self.bucket()
        return min(
            candidates,
            key=lambda c: (
                int(loads.get(self._as_uuid(c.id), 0)),
                self._entry_tiebreak(user_id=user_id, entry_id=c.id, bucket=bucket),
            ),
        )

    @staticmethod
    def _as_uuid(value: object) -> UUID:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        raise TypeError(f"Expected UUID-compatible value, got {type(value)!r}")

    @staticmethod
    def _is_entry_usable(entry) -> bool:
        if entry is None:
            return False
        if not entry.is_active:
            return False
        if not entry.is_enabled:
            return False
        if entry.is_draining:
            return False
        if entry.is_virtual:
            return True
        agent = entry.agent_state
        return agent is None or agent.is_healthy is not False

    @staticmethod
    def _entry_tiebreak(*, user_id, entry_id, bucket: int | None) -> int:
        seed = f"{user_id}:{bucket}:{entry_id}" if bucket is not None else f"{user_id}:{entry_id}"
        return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")
