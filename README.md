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
- Strict mode: `/api/v1/agent/initial` requires stable `X-Node-Key` and `X-Agent-Instance-ID` headers (no source-IP identity fallback).

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
