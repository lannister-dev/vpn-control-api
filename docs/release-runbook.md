# Release Runbook (MVP)

## 1. Preconditions

- Migrations applied (`alembic upgrade head`).
- At least one backend node is active/enabled/not draining.
- Admin auth token is available.
- Active profiles artifact exists in DB.

## 2. Apply migrations

Preferred path: run migrations from GitHub Actions UI.

Development:
1. Open GitHub Actions.
2. Run workflow `Dev DB Migrate`.
3. Choose:
   - `image_tag=dev` or a specific image tag
   - `alembic_command=upgrade head`

Production:
1. Open GitHub Actions.
2. Run workflow `Prod DB Migrate`.
3. Choose:
   - `image_tag=prod` or a specific image tag
   - `alembic_command=upgrade head`

Fallback shell path for dev on a Swarm manager:
```bash
docker run --rm \
  --network data-dev-net \
  --env-file .env.dev \
  harbor.lannister-dev.ru/vpn-service/control-api:${IMAGE_TAG:-dev} \
  alembic upgrade head
```

Fallback shell path for prod on a Swarm manager:
```bash
docker run --rm \
  --network data-prod-net \
  --env-file .env.prod \
  harbor.lannister-dev.ru/vpn-service/control-api:${IMAGE_TAG:-prod} \
  alembic upgrade head
```

Check current revision manually:
```bash
docker run --rm \
  --network data-dev-net \
  --env-file .env.dev \
  harbor.lannister-dev.ru/vpn-service/control-api:${IMAGE_TAG:-dev} \
  alembic current
```

## 3. Create schema in dev and import old data

Use this flow when there is an old PostgreSQL instance with current data that must be copied into the new dev DB.

Principle:
- schema is created by Alembic in the target DB
- data is copied separately from the old DB
- do not restore source schema on top of an Alembic-managed target

1. Create target schema first:
```bash
docker run --rm \
  --network data-dev-net \
  --env-file .env.dev \
  harbor.lannister-dev.ru/vpn-service/control-api:${IMAGE_TAG:-dev} \
  alembic upgrade head
```

2. Dump data from the old PostgreSQL into a local file:
```bash
PGPASSWORD='<OLD_DB_PASSWORD>' pg_dump \
  --host <OLD_DB_HOST> \
  --port <OLD_DB_PORT> \
  --username <OLD_DB_USER> \
  --dbname <OLD_DB_NAME> \
  --data-only \
  --no-owner \
  --no-privileges \
  --format=custom \
  --file /tmp/vpn-control-dev-data.dump
```

3. Restore data into the new dev PostgreSQL:
```bash
docker run --rm \
  --network data-dev-net \
  -v /tmp:/tmp \
  -e PGPASSWORD='<DEV_DB_PASSWORD>' \
  postgres:16-alpine \
  pg_restore \
  --host postgres-dev \
  --port 5432 \
  --username vpn_dev_user \
  --dbname vpn_control_dev \
  --data-only \
  --no-owner \
  --no-privileges \
  /tmp/vpn-control-dev-data.dump
```

4. Verify that tables contain rows:
```bash
docker run --rm \
  --network data-dev-net \
  -e PGPASSWORD='<DEV_DB_PASSWORD>' \
  postgres:16-alpine \
  psql \
  --host postgres-dev \
  --port 5432 \
  --username vpn_dev_user \
  --dbname vpn_control_dev \
  -c '\\dt' \
  -c 'select count(*) from alembic_version;'
```

Notes:
- replace `<OLD_DB_*>` with credentials of the old PostgreSQL
- replace `<DEV_DB_PASSWORD>` with the password of `vpn_dev_user`
- if the old DB schema is not compatible with current Alembic revisions, do not restore blindly; first compare table set and columns
- if you need a full one-time copy including schema for forensic work, restore into a separate disposable DB, not into the Alembic-managed dev DB

## 4. Bootstrap profiles and routes

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

## 5. Smoke checks

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

## 6. Rollback

1. Re-publish previous known-good artifact.
2. Reload registry.
3. Re-run bootstrap-routes for that artifact.
4. Verify `/connect` returns stable routes.

## 7. Mandatory checks before launch

- `pytest -q`
- `/api/readyz` returns `200` (DB + Redis live)
- `/api/monitoring` reachable
- `/api/v1/admin/readiness` returns `ready: true`
- At least one healthy backend route per active region
- Probe ingestion path works with valid token
