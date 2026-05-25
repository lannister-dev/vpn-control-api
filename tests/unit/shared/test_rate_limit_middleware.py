from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from shared.middlewares.rate_limit import (
    InMemorySlidingWindowLimiter,
    PathPrefixRateLimitMiddleware,
    RateLimitRule,
)


def _build_app(rules):
    app = FastAPI()
    app.add_middleware(
        PathPrefixRateLimitMiddleware,
        rules=rules,
        limiter=InMemorySlidingWindowLimiter(),
    )

    @app.get("/api/v1/billing/webhooks/foo")
    def webhook():
        return {"ok": True}

    @app.get("/api/v1/other")
    def other():
        return {"ok": True}

    return app


def test_under_limit_passes_through():
    app = _build_app([
        RateLimitRule("/api/v1/billing/webhooks/", max_requests=3, window_sec=60),
    ])
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/api/v1/billing/webhooks/foo").status_code == 200


def test_over_limit_returns_429():
    app = _build_app([
        RateLimitRule("/api/v1/billing/webhooks/", max_requests=2, window_sec=60),
    ])
    with TestClient(app) as client:
        client.get("/api/v1/billing/webhooks/foo")
        client.get("/api/v1/billing/webhooks/foo")
        resp = client.get("/api/v1/billing/webhooks/foo")
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Rate limit exceeded"
    assert resp.headers["Retry-After"] == "60"


def test_unmatched_path_not_throttled():
    app = _build_app([
        RateLimitRule("/api/v1/billing/webhooks/", max_requests=1, window_sec=60),
    ])
    with TestClient(app) as client:
        for _ in range(20):
            assert client.get("/api/v1/other").status_code == 200


def test_first_matching_rule_wins():
    app = _build_app([
        RateLimitRule("/api/v1/billing/webhooks/foo", max_requests=1, window_sec=60),
        RateLimitRule("/api/v1/billing/webhooks/", max_requests=10, window_sec=60),
    ])
    with TestClient(app) as client:
        assert client.get("/api/v1/billing/webhooks/foo").status_code == 200
        assert client.get("/api/v1/billing/webhooks/foo").status_code == 429


def test_per_ip_isolation():
    app = _build_app([
        RateLimitRule("/api/v1/billing/webhooks/", max_requests=1, window_sec=60),
    ])
    with TestClient(app) as client:
        r1 = client.get("/api/v1/billing/webhooks/foo", headers={"x-forwarded-for": "10.0.0.1"})
        r2 = client.get("/api/v1/billing/webhooks/foo", headers={"x-forwarded-for": "10.0.0.2"})
        r3 = client.get("/api/v1/billing/webhooks/foo", headers={"x-forwarded-for": "10.0.0.1"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
