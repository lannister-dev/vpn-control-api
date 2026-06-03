from __future__ import annotations

import logging

from services.balancer.policy import BalancerPolicy
from services.balancer.repository import BalancerRepository
from services.balancer.types import BalancePlan
from services.config import BalancerConfig
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("balancer"))


class BalancerService:
    def __init__(self, *, config: BalancerConfig, session_maker=None) -> None:
        self._cfg = config
        self._policy = BalancerPolicy(config)
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()

    async def run_once(self) -> BalancePlan:
        async with self._session_maker() as session:
            repo = BalancerRepository(session)
            nodes = await repo.load_nodes(window_sec=self._cfg.window_sec)
            if len(nodes) < 2:
                return BalancePlan(skipped_reason="need_two_nodes")

            name_by_id = {n.node_id: n.name for n in nodes}
            keys = await repo.load_keys(
                window_sec=self._cfg.window_sec,
                cooldown_sec=self._cfg.cooldown_sec,
                live_node_ids=set(name_by_id),
                node_name_by_id=name_by_id,
            )
            plan = self._policy.plan(nodes, keys)
            if plan.moves:
                await repo.apply_moves(plan.moves)
                logger.info(
                    "balancer_applied",
                    moves=len(plan.moves),
                    deviations={str(k): v for k, v in plan.deviations.items()},
                )
            return plan
