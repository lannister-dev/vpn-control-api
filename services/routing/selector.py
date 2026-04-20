from __future__ import annotations

import random
from collections.abc import Callable
from typing import Generic, TypeVar
from uuid import UUID

RouteItemT = TypeVar("RouteItemT")
TransportKey = tuple[str, str]
EntryKey = UUID | None


class RouteSelector(Generic[RouteItemT]):
    def __init__(
            self,
            *,
            get_backend_id: Callable[[RouteItemT], UUID],
            get_transport_key: Callable[[RouteItemT], TransportKey],
            get_route_id: Callable[[RouteItemT], UUID],
            get_weight: Callable[[RouteItemT], float] | None = None,
            get_entry_key: Callable[[RouteItemT], EntryKey] | None = None,
    ):
        self._get_backend_id = get_backend_id
        self._get_transport_key = get_transport_key
        self._get_route_id = get_route_id
        self._get_weight = get_weight or (lambda _item: 1.0)
        self._get_entry_key = get_entry_key or (lambda _item: None)

    def select(
            self,
            *,
            routes: list[RouteItemT],
            preferred_backend_id: UUID,
            max_routes: int,
            seed: object = None,
    ) -> list[RouteItemT]:
        if max_routes <= 0:
            return []
        if max_routes == 1:
            return routes[:1]

        rng = self._make_rng(seed) if seed is not None else None

        primary = [route for route in routes if self._get_backend_id(route) == preferred_backend_id]
        fallback = [route for route in routes if self._get_backend_id(route) != preferred_backend_id]

        primary_target = min(2, max_routes - 1, len(primary))
        fallback_target = min(max_routes - primary_target, len(fallback))

        selected: list[RouteItemT] = []
        selected.extend(self._weighted_entry_diversity_pick(primary, limit=primary_target, rng=rng))

        selected_fallback, fallback_remainder = self._select_fallback_with_backend_diversity(
            fallback=fallback,
            limit=fallback_target,
            rng=rng,
        )
        selected.extend(selected_fallback)

        if len(selected) < max_routes:
            selected_ids = {self._get_route_id(r) for r in selected}
            primary_remainder = [r for r in primary if self._get_route_id(r) not in selected_ids]
            selected.extend(primary_remainder[: max_routes - len(selected)])
            if len(selected) < max_routes:
                selected.extend(fallback_remainder[: max_routes - len(selected)])

        selected = selected[:max_routes]
        return self._ensure_transport_insurance(
            selected=selected,
            all_routes=routes,
            preferred_backend_id=preferred_backend_id,
            max_routes=max_routes,
        )

    def _make_rng(self, seed: object) -> random.Random:
        if isinstance(seed, UUID):
            return random.Random(seed.int)
        if isinstance(seed, int):
            return random.Random(seed)
        return random.Random(hash(str(seed)))

    def _weighted_pick(
            self,
            candidates: list[RouteItemT],
            *,
            rng: random.Random | None,
    ) -> RouteItemT | None:
        if not candidates:
            return None
        if rng is None:
            return candidates[0]
        weights = [max(0.0, float(self._get_weight(c))) for c in candidates]
        total = sum(weights)
        if total <= 0.0:
            return rng.choice(candidates)
        return rng.choices(candidates, weights=weights, k=1)[0]

    def _weighted_entry_diversity_pick(
            self,
            candidates: list[RouteItemT],
            *,
            limit: int,
            rng: random.Random | None,
    ) -> list[RouteItemT]:
        if limit <= 0 or not candidates:
            return []
        pool = list(candidates)
        selected: list[RouteItemT] = []
        used_entries: set[EntryKey] = set()
        while pool and len(selected) < limit:
            preferred = [r for r in pool if self._get_entry_key(r) not in used_entries]
            bucket = preferred if preferred else pool
            pick = self._weighted_pick(bucket, rng=rng)
            if pick is None:
                break
            selected.append(pick)
            used_entries.add(self._get_entry_key(pick))
            pick_id = self._get_route_id(pick)
            pool = [r for r in pool if self._get_route_id(r) != pick_id]
        return selected

    def _ensure_transport_insurance(
            self,
            *,
            selected: list[RouteItemT],
            all_routes: list[RouteItemT],
            preferred_backend_id: UUID,
            max_routes: int,
    ) -> list[RouteItemT]:
        if len(selected) < 2:
            return selected

        primary_transport = self._get_transport_key(selected[0])
        if any(self._get_transport_key(route) != primary_transport for route in selected[1:]):
            return selected

        selected_ids = {self._get_route_id(route) for route in selected}
        candidates = [route for route in all_routes if self._get_route_id(route) not in selected_ids]
        candidates = [
            route
            for route in candidates
            if self._get_transport_key(route) != primary_transport
        ]
        if not candidates:
            return selected

        insurance = next(
            (route for route in candidates if self._get_backend_id(route) != preferred_backend_id),
            candidates[0],
        )

        if len(selected) < max_routes:
            return [*selected, insurance]

        replace_idx = None
        for idx in range(len(selected) - 1, 0, -1):
            if self._get_transport_key(selected[idx]) == primary_transport:
                replace_idx = idx
                break
        if replace_idx is None:
            replace_idx = len(selected) - 1
        selected[replace_idx] = insurance
        return selected

    def _select_fallback_with_backend_diversity(
            self,
            *,
            fallback: list[RouteItemT],
            limit: int,
            rng: random.Random | None,
    ) -> tuple[list[RouteItemT], list[RouteItemT]]:
        if limit <= 0:
            return [], list(fallback)

        pool = list(fallback)
        selected: list[RouteItemT] = []
        used_backends: set[UUID] = set()

        while pool and len(selected) < limit:
            preferred = [r for r in pool if self._get_backend_id(r) not in used_backends]
            bucket = preferred if preferred else pool
            pick = self._weighted_pick(bucket, rng=rng)
            if pick is None:
                break
            selected.append(pick)
            used_backends.add(self._get_backend_id(pick))
            pick_id = self._get_route_id(pick)
            pool = [r for r in pool if self._get_route_id(r) != pick_id]

        remainder = pool
        return selected, remainder
