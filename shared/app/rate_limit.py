from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass(frozen=True)
class RateLimitRule:
    """Rate limit for a path prefix.

    Match is performed by `path.startswith(prefix)`. The first matching rule
    wins; specify more specific prefixes earlier in the list. Key is composed
    of `(client_ip, prefix)` so different rules are tracked independently.
    """

    prefix: str
    max_requests: int
    window_sec: int


class InMemorySlidingWindowLimiter:
    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str, *, max_requests: int, window_sec: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = [t for t in self._buckets[key] if now - t < window_sec]
            if len(bucket) >= max_requests:
                self._buckets[key] = bucket
                return False
            bucket.append(now)
            self._buckets[key] = bucket
            return True


class PathPrefixRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-IP sliding window rate limits to selected path prefixes.

    Storage is in-process: in a multi-replica deployment each pod enforces its
    own quota. That is acceptable for abuse mitigation (an attacker hitting one
    pod still gets blocked there); for strict global enforcement use Redis-
    backed limiter behind an ingress.
    """

    def __init__(self, app, rules: list[RateLimitRule], limiter: InMemorySlidingWindowLimiter | None = None):
        super().__init__(app)
        self._rules = rules
        self._limiter = limiter or InMemorySlidingWindowLimiter()

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        rule = self._match(path)
        if rule is None:
            return await call_next(request)

        client_ip = self._client_ip(request)
        key = f"{rule.prefix}|{client_ip}"
        if not self._limiter.is_allowed(
            key,
            max_requests=rule.max_requests,
            window_sec=rule.window_sec,
        ):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(rule.window_sec)},
            )
        return await call_next(request)

    def _match(self, path: str) -> RateLimitRule | None:
        for rule in self._rules:
            if path.startswith(rule.prefix):
                return rule
        return None

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"


DEFAULT_API_RULES: list[RateLimitRule] = [
    RateLimitRule(prefix="/api/v1/billing/webhooks/", max_requests=120, window_sec=60),
    RateLimitRule(prefix="/api/v1/auth/admin/login/telegram", max_requests=10, window_sec=60),
    RateLimitRule(prefix="/api/v1/subscriptions/", max_requests=120, window_sec=60),
    RateLimitRule(prefix="/api/v1/agent/initial", max_requests=30, window_sec=60),
    RateLimitRule(prefix="/api/v1/agent/install.sh", max_requests=20, window_sec=60),
]


def add_default_rate_limit(app) -> None:
    app.add_middleware(PathPrefixRateLimitMiddleware, rules=DEFAULT_API_RULES)
