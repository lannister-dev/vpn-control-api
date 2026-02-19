# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

VPN control plane API that manages VPN nodes, keys, subscriptions, and client configurations. Uses a **desired-state reconciliation model**: the control plane defines what should exist, and node agents report back what actually exists (desired_state → applied_state, with pending/applied/failed status).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (auto-reload)
python app.py
# OR: uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# Database migrations
alembic upgrade head              # Apply all migrations
alembic revision --autogenerate -m "description"  # Create migration
alembic downgrade -1              # Rollback one

# Docker
docker build -t vpn-control-api .
docker-compose up -d
```

No test suite exists yet. If adding tests, use `pytest` + `pytest-asyncio` + `httpx`.

## Architecture

**Stack:** Python 3.10, FastAPI (async), SQLAlchemy 2.0 (async/asyncpg), PostgreSQL, Redis, Alembic.

**Entry point:** `app.py` — creates FastAPI app, registers routers under `/api/v1`, initializes Redis and profiles registry on startup.

**Layered structure per domain module in `services/`:**
- `router.py` → `service.py` → `repository.py` → `models.py` + `schemas.py`
- Dependencies injected via FastAPI `Depends()` — session provided by `AsyncDatabase.get_session`

**Domain modules (`services/`):**
- `auth/` — Two auth schemes: admin (Bearer + SHA-256 hash) and node (Bearer + X-Node-ID header). Timing-safe comparison via `secrets.compare_digest`.
- `nodes/` — VPN node lifecycle, agent bootstrap (idempotent, rotates token), heartbeat, assignment reconciliation reporting.
- `vpn/keys/` — VPN key CRUD, key-to-node assignment with desired/applied state tracking, revocation.
- `vpn/subscriptions/` — Client subscription tokens, VLESS URI delivery, ETag support, Redis rate limiting, token rotation with grace period.
- `artifacts/` — Profile artifact versioning with publish/activate workflow, checksum dedup.
- `users/` — User model (telegram_id, balance).

**Shared infrastructure (`shared/`):**
- `database/` — AsyncDatabase session manager (pool: 50, overflow: 25, pre-ping), BaseRepository with generic CRUD + PostgreSQL upsert, Base model (auto UUID pk, timestamps, soft delete `is_active`).
- `redis/` — Async client for distributed locking (context manager with TTL+NX), caching, rate limiting.
- `profiles/` — In-memory VPN profile registry (WS-TLS, Reality TCP), VLESS URI builder, bootstraps from DB artifacts on startup.
- `utils/` — Structured JSON logger: `log.info("message", key=value)`.

**Config:** `services/config.py` — environs (marshmallow) with `@lru_cache` dataclass sections (Database, Redis, Admin, ProfilesVPN). Reads from `.env`.

**API docs:** Swagger at `/api/docs`, metrics at `/api/metrics` (Prometheus).

## Conventions

- **Commit messages:** `<type>(<scope>): <description>` (e.g., `fix(api):`, `feat(vpn):`, `refactor(profiles):`)
- **All DB operations are async** — use `await` with SQLAlchemy async sessions
- **Idempotency** via PostgreSQL `ON CONFLICT` upserts with `op_version` increment
- **State tracking** fields: `desired_state`, `applied_state`, `status` (pending/applied/failed), `attempts`, `next_retry_at`
- **Route protection** via `Depends(admin_auth)` or `Depends(node_auth)` dependency injection
