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

Config notes:
- Use `PROBE_TARGET_PORT` (legacy `DEFAULT_TARGET_PORT` is still supported for backward compatibility).
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
