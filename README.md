# vpn-control-api

## Quick Start

1. Copy env template:
```bash
cp .env.example .env
```
2. Apply migrations:
```bash
alembic upgrade head
```
3. Run tests:
```bash
pytest -q
```

Docker build note:
- If Docker Hub starts returning `429 Too Many Requests` on `python:3.10*`, build with mirrored base images via `--build-arg PYTHON_BUILD_IMAGE=... --build-arg PYTHON_RUNTIME_IMAGE=...` instead of editing the `Dockerfile`.

Config notes:
- Use `PROBE_TARGET_PORT` (legacy `DEFAULT_TARGET_PORT` is still supported for backward compatibility).
- `/api/v1/probe/targets` accepts optional `role`; current semantics are explicit `vpn_node.role` filtering (`backend`, `whitelist_entry`, `gateway`, or `all`).
- `whitelist_entry` targets are node-scoped `tcp_connect` checks; backend targets remain route/transport-scoped and may carry synthetic probe credentials.
- `PROBE_SYNTHETIC_REALITY_CLIENT_ID` / `PROBE_SYNTHETIC_WS_CLIENT_ID` let `/api/v1/probe/targets` attach a real probe `client_id` for synthetic checks, but only when that key is active and already synced to the backend node.
- `PROBE_SYNTHETIC_RECONCILE_ENABLED=true` starts a background reconciler that creates/keeps the synthetic probe keys and placements aligned across all probeable backends for the configured transports.
- Current node-agent placements endpoint is `GET /api/v1/agent/placements/page`.
- For multi-agent-per-node rollout, pass stable `X-Agent-Instance-ID` UUID on `/api/v1/agent/initial` and all authenticated `/api/v1/agent/*` calls.
- For authenticated `/api/v1/agent/*` calls, `X-Node-ID` is recommended. If it is temporarily missing, API can resolve node from `(X-Agent-Instance-ID + token)` without 422 loops.
- Strict mode: `/api/v1/agent/initial` requires stable `X-Node-Key` and `X-Agent-Instance-ID` headers (no source-IP identity fallback).
- Safety recovery: if `X-Node-Key` is new but exactly one existing node has the same source IP, bootstrap reuses that node and rebinds its `node_key`; if multiple nodes share source IP, bootstrap returns `409` to prevent accidental placement orphaning.
- Production hardening: set `NODE_BOOTSTRAP_ALLOW_CREATE=false` to block silent creation of unknown nodes. In this mode bootstrap returns `409` until a stable `AGENT_NODE_KEY` is provided.
- Heartbeat anti-flap: `NODE_HEARTBEAT_UNHEALTHY_DRAIN_THRESHOLD` controls how many consecutive unhealthy heartbeats are required before auto-drain; `NODE_HEARTBEAT_HEALTHY_UNDRAIN_THRESHOLD` controls recovery count for auto-undrain.
- Auto-heal mode: set `NODE_AUTO_HEAL_ENABLED=true` to enable background stale-node handling (`NODE_STALE_AFTER_SEC`) and automatic placement migration from unavailable backends.
- Auto-undrain mode: set `NODE_AUTO_UNDRAIN_ENABLED=true` to automatically return recovered healthy backend nodes from `draining` to active routing.
- Admin web panel is available at `GET /api/v1/admin/panel` (enter admin bearer token inside UI to fetch stats and run control actions).

## Artifact to Routes Bootstrap

Admin endpoint for syncing transport profiles and deterministic auto-routes from the active profile artifact:

`POST /api/v1/artifacts/profiles/bootstrap-routes`

Example payload:

```json
{
  "dry_run": false,
  "include_reality_tcp": true,
  "include_ws_tls": false,
  "default_reality_port": 443,
  "expected_backends_selected": 7,
  "expected_profiles_selected": 3,
  "expected_routes_total": 21,
  "profile_port_overrides": {
    "reality-microsoft": 8443,
    "reality-apple": 2053
  },
  "route_base_weight": 50
}
```

What it does:
- Reads active profile artifact from DB.
- Upserts `transport_profile` rows for eligible profiles.
- Upserts `route` rows for eligible backend nodes.
- Returns counters for created, updated, reactivated, and skipped records.
- Fails with `409` on matrix drift when `expected_*` assertions do not match.

## Release Readiness

- Smoke test path: `tests/unit/test_release_readiness_smoke.py`
- Runbook: `docs/release-runbook.md`
- Runtime orchestrator gate: `GET /api/readyz` (DB + Redis)
- Runtime gate endpoint: `GET /api/v1/admin/readiness`
- Expected baseline before launch: `pytest -q` is green and bootstrap dry-run/apply completed.

## Git Workflow (dev-first)

- Work only in personal branches (`feature/*`, `fix/*`, `chore/*`).
- Open Pull Request from personal branch to `dev`.
- CI workflow `Dev PR Checks` runs automatically and must be green.
- Merge into `dev` only after successful checks.

Recommended GitHub branch protection for `dev`:
- Require a pull request before merging.
- Require status checks to pass before merging: `tests`.
- Restrict who can push to `dev` (disable direct push for contributors).

## Delivery

- CI for `dev` branch and PRs into `dev`: `.github/workflows/dev-pr.yml`
- CD for development environment: `.github/workflows/dev-deploy.yml`
- CD for production environment: `.github/workflows/prod.yml`
  - triggers on push to `dev` and manual `workflow_dispatch`
  - runs tests before deploy
  - builds and pushes image tags `<sha7>` and `:dev`
  - loads Harbor credentials and runtime env from Vault path `kv/data/control-api/dev`
  - deploys Docker Swarm stack `control-api-dev` using `docker-compose.dev.yml`
- Manual DB migrations for development: `.github/workflows/dev-migrate.yml`
  - loads Harbor credentials and runtime env from Vault path `kv/data/control-api/dev`
  - runs `alembic` inside `data-dev-net` using selected image tag
- Manual DB migrations for production: `.github/workflows/prod-migrate.yml`
  - loads Harbor credentials and runtime env from Vault path `kv/data/control-api/prod`
  - runs `alembic` inside `data-prod-net` using selected image tag

Runner prerequisites for Vault-backed deploys:
- `VAULT_ADDR`
- `VAULT_ROLE_ID`
- `VAULT_SECRET_ID`

Required Vault fields:
- `kv/data/control-api/dev#config`
- `kv/data/control-api/dev#harbor_url`
- `kv/data/control-api/dev#harbor_project`
- `kv/data/control-api/dev#harbor_username`
- `kv/data/control-api/dev#harbor_password`
- `kv/data/control-api/prod#config`
- `kv/data/control-api/prod#harbor_url`
- `kv/data/control-api/prod#harbor_project`
- `kv/data/control-api/prod#harbor_username`
- `kv/data/control-api/prod#harbor_password`

Use local `.env.dev` and `.env.prod` as the source shape for Vault `config`.

Local dev deploy (Swarm):
- prepare env file: `.env.dev`
- deploy: `docker stack deploy --with-registry-auth --prune -c docker-compose.dev.yml control-api-dev`
- DB migrations and data import commands: `docs/release-runbook.md`

Local prod deploy (Swarm):
- prepare env file: `.env.prod`
- deploy: `docker stack deploy --with-registry-auth --prune -c docker-compose.yml control-api`
