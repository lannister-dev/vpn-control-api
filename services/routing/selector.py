from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar
from uuid import UUID

RouteItemT = TypeVar("RouteItemT")
TransportKey = tuple[str, str]


class RouteSelector(Generic[RouteItemT]):
    def __init__(
            self,
            *,
            get_backend_id: Callable[[RouteItemT], UUID],
            get_transport_key: Callable[[RouteItemT], TransportKey],
            get_route_id: Callable[[RouteItemT], UUID],
    ):
        self._get_backend_id = get_backend_id
        self._get_transport_key = get_transport_key
        self._get_route_id = get_route_id

    def select(
            self,
            *,
            routes: list[RouteItemT],
            preferred_backend_id: UUID,
            max_routes: int,
    ) -> list[RouteItemT]:
        if max_routes <= 0:
            return []
        if max_routes == 1:
            return routes[:1]

        primary = [route for route in routes if self._get_backend_id(route) == preferred_backend_id]
        fallback = [route for route in routes if self._get_backend_id(route) != preferred_backend_id]

        primary_target = min(2, max_routes - 1, len(primary))
        fallback_target = min(max_routes - primary_target, len(fallback))

        selected: list[RouteItemT] = []
        selected.extend(primary[:primary_target])

        selected_fallback, fallback_remainder = self._select_fallback_with_backend_diversity(
            fallback=fallback,
            limit=fallback_target,
        )
        selected.extend(selected_fallback)

        if len(selected) < max_routes:
            primary_remainder = primary[primary_target:]
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
    ) -> tuple[list[RouteItemT], list[RouteItemT]]:
        if limit <= 0:
            return [], fallback

        selected: list[RouteItemT] = []
        remainder: list[RouteItemT] = []
        used_backends: set[UUID] = set()

        for route in fallback:
            backend_id = self._get_backend_id(route)
            if len(selected) < limit and backend_id not in used_backends:
                selected.append(route)
                used_backends.add(backend_id)
            else:
                remainder.append(route)

        if len(selected) < limit and remainder:
            needed = limit - len(selected)
            selected.extend(remainder[:needed])
            remainder = remainder[needed:]

        return selected, remainder
