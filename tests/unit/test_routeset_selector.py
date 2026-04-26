from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from services.routing.selector import RouteSelector


@dataclass(frozen=True)
class _Item:
    route_id: UUID
    backend_id: UUID
    security: str
    network: str


def _route(
        *,
        backend_id: UUID,
        security: str = "reality",
        network: str = "tcp",
) -> _Item:
    return _Item(
        route_id=uuid4(),
        backend_id=backend_id,
        security=security,
        network=network,
    )


def _make_selector() -> RouteSelector[_Item]:
    return RouteSelector(
        get_backend_id=lambda item: item.backend_id,
        get_transport_key=lambda item: (item.security, item.network),
        get_route_id=lambda item: item.route_id,
    )


def test_selector_prefers_primary_and_fallback_backend_diversity():
    primary_backend = uuid4()
    fallback_backend_1 = uuid4()
    fallback_backend_2 = uuid4()

    routes = [
        _route(backend_id=primary_backend),
        _route(backend_id=primary_backend),
        _route(backend_id=fallback_backend_1),
        _route(backend_id=fallback_backend_1),
        _route(backend_id=fallback_backend_2),
    ]

    out = _make_selector().select(
        routes=routes,
        preferred_backend_id=primary_backend,
        max_routes=4,
    )

    assert len(out) == 4
    assert out[0].backend_id == primary_backend
    assert out[1].backend_id == primary_backend
    assert out[2].backend_id == fallback_backend_1
    assert out[3].backend_id == fallback_backend_2


def test_selector_adds_transport_insurance_when_selected_routes_share_transport():
    primary_backend = uuid4()
    fallback_backend = uuid4()

    primary_a = _route(backend_id=primary_backend, security="reality", network="tcp")
    primary_b = _route(backend_id=primary_backend, security="reality", network="tcp")
    fallback_same = _route(backend_id=fallback_backend, security="reality", network="tcp")
    insurance = _route(backend_id=fallback_backend, security="tls", network="grpc")

    out = _make_selector().select(
        routes=[primary_a, primary_b, fallback_same, insurance],
        preferred_backend_id=primary_backend,
        max_routes=3,
    )

    assert len(out) == 3
    assert (out[0].security, out[0].network) == ("reality", "tcp")
    assert (out[1].security, out[1].network) == ("reality", "tcp")
    assert (out[2].security, out[2].network) == ("tls", "grpc")


def test_selector_respects_single_route_mode():
    primary_backend = uuid4()
    routes = [
        _route(backend_id=primary_backend),
        _route(backend_id=uuid4()),
    ]

    out = _make_selector().select(
        routes=routes,
        preferred_backend_id=primary_backend,
        max_routes=1,
    )

    assert out == [routes[0]]
