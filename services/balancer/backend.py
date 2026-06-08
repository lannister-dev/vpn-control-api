from __future__ import annotations

import hashlib
import logging

from pydantic import ValidationError

from services.balancer.selection import BackendCandidate, choose_backend_tag
from services.routing.entry.constants import KV_STATS_BUCKET
from services.routing.entry.schemas import EntryRoutingStatsKv
from services.vpn.keys.schemas import VpnKeyRoutingOverrideUpdate
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("balancer.backend"))


class BackendBalancer:
    def __init__(self, *, nats=None, vpn_key_repository):
        self._nats = nats
        self._vpn_key_repository = vpn_key_repository

    @staticmethod
    async def fetch_backend_loads(nats) -> dict[str, int]:
        loads: dict[str, int] = {}
        if nats is None:
            return loads
        try:
            entries = await nats.kv_list_all(bucket=KV_STATS_BUCKET)
        except Exception:
            logger.exception("backend_loads_fetch_failed")
            return loads
        for raw in entries.values():
            try:
                stats = EntryRoutingStatsKv.model_validate_json(raw)
            except ValidationError:
                continue
            for tag, count in stats.by_backend.items():
                loads[tag] = loads.get(tag, 0) + count
        return loads

    @staticmethod
    def build_candidates(
            *,
            key_id,
            allowed_backend_ids,
            nodes_by_id: dict,
            backend_loads: dict[str, int],
    ) -> list[BackendCandidate]:
        candidates: list[BackendCandidate] = []
        for bid in allowed_backend_ids or ():
            node = nodes_by_id.get(bid)
            if node is None or not node.is_enabled or node.is_draining:
                continue
            tag = f"backend-{node.name}"
            candidates.append(BackendCandidate(
                tag=tag,
                load=backend_loads.get(tag, 0),
                tiebreak=BackendBalancer._tiebreak(key_id=key_id, backend_id=node.id),
            ))
        return candidates

    async def assign_key_backend(
            self,
            *,
            key_id,
            allowed_backend_ids,
            nodes_by_id: dict,
            backend_loads: dict[str, int],
    ) -> str | None:
        if not allowed_backend_ids:
            return None
        candidates = self.build_candidates(
            key_id=key_id,
            allowed_backend_ids=allowed_backend_ids,
            nodes_by_id=nodes_by_id,
            backend_loads=backend_loads,
        )
        if not candidates:
            return None
        try:
            vpn_key = await self._vpn_key_repository.get_by_id(key_id)
            if vpn_key is None:
                return None
            current_tag = vpn_key.entry_routing_override_backend_tag
            chosen_tag = choose_backend_tag(candidates, current_tag=current_tag)
            if current_tag != chosen_tag:
                await self._vpn_key_repository.update_by_id(
                    key_id,
                    VpnKeyRoutingOverrideUpdate(
                        entry_routing_override_backend_tag=chosen_tag,
                    ).model_dump(exclude_unset=True),
                )
        except Exception:
            logger.exception("backend_override_update_failed", key_id=str(key_id))
            return None
        if chosen_tag is not None:
            backend_loads[chosen_tag] = backend_loads.get(chosen_tag, 0) + 1
        return chosen_tag

    @staticmethod
    def _tiebreak(*, key_id, backend_id) -> int:
        seed = f"{key_id}:{backend_id}"
        return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")
