# Release Runbook (MVP)

## 1. Preconditions

- Migrations applied (`alembic upgrade head`).
- At least one backend node is active/enabled/not draining.
- Admin auth token is available.
- Active profiles artifact exists in DB.

## 2. Bootstrap profiles and routes

1. Publish artifact:
```bash
curl -X POST "$API/api/v1/artifacts/profiles/publish" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d @artifact.json
```

2. Reload in-memory registry:
```bash
curl -X POST "$API/api/v1/artifacts/profiles/reload" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

3. Dry-run routes bootstrap:
```bash
curl -X POST "$API/api/v1/artifacts/profiles/bootstrap-routes" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true, "include_reality_tcp": true, "include_ws_tls": false, "expected_profiles_selected": 3, "expected_backends_selected": 7, "expected_routes_total": 21}'
```

4. Apply bootstrap:
```bash
curl -X POST "$API/api/v1/artifacts/profiles/bootstrap-routes" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "include_reality_tcp": true, "include_ws_tls": false, "expected_profiles_selected": 3, "expected_backends_selected": 7, "expected_routes_total": 21}'
```

Notes:
- Replace `3/7/21` with your target release matrix.
- `409 Bootstrap matrix mismatch` means infra/artifact state drifted from planned launch matrix.

## 3. Smoke checks

1. Backend status:
```bash
curl -X GET "$API/api/v1/admin/status" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

2. Launch readiness (must be `ready: true`):
```bash
curl -X GET "$API/api/v1/admin/readiness" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

3. Resolve routeset:
```bash
curl -X POST "$API/api/v1/connect" \
  -H "Authorization: Bearer $CONNECT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"<uuid>","max_routes":3}'
```

4. Optional telemetry event:
```bash
curl -X POST "$API/api/v1/connect/telemetry" \
  -H "Authorization: Bearer $CONNECT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key_id":"<uuid>","route_id":"<uuid>","event":"connect_failure"}'
```

## 4. Rollback

1. Re-publish previous known-good artifact.
2. Reload registry.
3. Re-run bootstrap-routes for that artifact.
4. Verify `/connect` returns stable routes.

## 5. Mandatory checks before launch

- `pytest -q`
- `/api/readyz` returns `200` (DB + Redis live)
- `/api/monitoring` reachable
- `/api/v1/admin/readiness` returns `ready: true`
- At least one healthy backend route per active region
- Probe ingestion path works with valid token
