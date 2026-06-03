from __future__ import annotations

from services.balancer.service import BalancerService
from services.config import BalancerConfig, get_settings
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock


class BalanceReconciler(Reconciler):
    name = "balancer"

    def __init__(
        self,
        *,
        config: BalancerConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        cfg = config or get_settings().balancer
        super().__init__(interval_sec=cfg.tick_sec, enabled=cfg.enabled, tick_lock=tick_lock)
        self._service = BalancerService(config=cfg)

    async def tick(self) -> int:
        plan = await self._service.run_once()
        return len(plan.moves)
