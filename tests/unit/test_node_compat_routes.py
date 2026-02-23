from app import app


def _has_route(*, path: str, method: str) -> bool:
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if route.path == path and methods and method in methods:
            return True
    return False


def test_node_compat_routes_registered():
    assert _has_route(path="/api/v1/agent/initial", method="POST")
    assert _has_route(path="/api/v1/agent/heartbeat", method="POST")
    assert _has_route(path="/api/v1/agent/sync-report", method="POST")
    assert _has_route(path="/api/v1/agent/placements/page", method="GET")
