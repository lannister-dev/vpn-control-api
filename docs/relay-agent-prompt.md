# Entry Relay — Go Agent Implementation Prompt

Copy-paste the section below into a fresh Claude Code session running inside the GoLand project where the relay binary will live. The prompt is self-contained: the Go agent does NOT need access to the `vpn-control-api` Python repository.

---

## Role

You are implementing an **Entry Relay** — a stateless Go TCP proxy that sits between VPN clients and backend Xray+REALITY nodes. The relay is part of a larger VPN control plane whose control API is Python/FastAPI (out of your scope). You own ONLY the Go binary, its Dockerfile, its Helm chart, its CI workflow, and its tests.

## Why this exists (one paragraph of context, don't over-read)

Clients currently connect directly to backend Xray nodes. That exposes backend IPs and every backend failure is visible to users. The relay fixes both: clients now connect to cheap, disposable entry nodes; each entry forwards TCP to one backend from a pool; a dead backend is silently swapped. REALITY key material is identical across all backends, so swapping is transparent. The relay does NOT parse TLS/REALITY/VLESS — pure TCP passthrough.

## Hard constraints (do not violate)

- **Pure TCP passthrough.** Do NOT terminate TLS. Do NOT parse VLESS/REALITY. Treat bytes as opaque.
- **Stateless.** No persistence on the relay. All authoritative state lives in control-api.
- **Survive control-api outage** for 5 minutes by caching the last-known pool in memory.
- **Zero-copy where possible.** Use `io.Copy` in both directions, one goroutine per direction per connection. On Linux, stdlib will use `splice(2)` automatically when both sides are `*net.TCPConn`.
- **Standard library + `github.com/prometheus/client_golang` only.** No frameworks, no service meshes, no extra logger deps (use `log/slog` with JSON handler).
- **Binary size target:** `< 20 MB`. **RAM at 1000 concurrent connections:** `< 500 MB`.

## API contract (control-api → relay)

The relay polls this endpoint every `RELAY_POOL_REFRESH_SEC` (default 30s):

```
GET {RELAY_CONTROL_API_URL}/api/v1/entry/{RELAY_ENTRY_ID}/backends
Authorization: Bearer {RELAY_CONTROL_API_TOKEN}
Accept: application/json
```

Success response (`200 OK`):

```json
{
  "entry_id": "2f2a0c7e-4d5b-4d0b-8a9a-0b9b4cfb2a01",
  "generation": 42,
  "ttl_seconds": 300,
  "backends": [
    {
      "id": "b5c4e3a2-1f00-4a11-9c33-aaaaaaaaaaaa",
      "address": "10.0.1.5",
      "port": 443,
      "weight": 100,
      "enabled": true
    }
  ]
}
```

- `address` is an IPv4/IPv6 string or a DNS name. Do a fresh DNS lookup on each dial (no caching in the relay; Linux resolver handles that).
- `weight` is a positive integer, used by the selection algorithm. Treat missing/<=0 as `1`.
- `enabled=false` backends must be excluded from selection even if healthy.
- `generation` monotonically increases on each pool change. Log `pool_updated generation=<N> backends=<M>` only when `generation` changes.
- `ttl_seconds` is advisory: if the relay cannot reach control-api, it MAY keep using the cached pool up to `max(ttl_seconds, 300)` seconds past the last successful fetch before marking itself unhealthy.

Error handling:
- 401/403 → log at ERROR, keep cached pool, do NOT crash.
- 5xx or network error → exponential backoff (1s → 2s → 5s → 10s → 30s cap), keep cached pool.
- On startup with NO cached pool and control-api unreachable, fail `/healthz` but keep retrying; do NOT exit.

## Runtime behaviour

**Listener:**
- Bind `RELAY_LISTEN_ADDR` (default `:443`) on TCP.
- `SO_REUSEPORT` is nice-to-have but not required.
- No TLS on this socket.

**Per connection:**
1. Select a backend (see selection).
2. `net.DialTimeout("tcp", addr, RELAY_DIAL_TIMEOUT)` (default 3s).
3. On dial failure: mark that backend `dial_failures++`, try next candidate up to `RELAY_DIAL_MAX_ATTEMPTS` (default 3). If all fail, close client conn, increment metric.
4. Two goroutines with `io.Copy` (`client→backend`, `backend→client`). On first `Copy` returning, call `CloseWrite` on the peer to half-close gracefully, then wait for the other direction with a `RELAY_HALF_CLOSE_TIMEOUT` (default 15s) deadline.
5. Always `defer conn.Close()` on both ends.

**Health checker (separate goroutine per relay, not per connection):**
- Every `RELAY_HEALTH_INTERVAL` (default 10s), dial `backend.address:backend.port` with `RELAY_HEALTH_TIMEOUT` (default 2s).
- State machine: `healthy` ⇄ `unhealthy`.
  - Healthy → unhealthy after `2` consecutive failures.
  - Unhealthy → healthy after `1` success.
- Track EWMA dial latency per backend for selection.
- Emit `relay_backend_up{backend_id}` gauge (0/1) and `relay_backend_latency_ms{backend_id}` gauge.

**Selection algorithm:**
- Filter: only `enabled=true` and `healthy=true`.
- Weighted random by `weight_i / max(latency_ewma_ms_i, 1)`.
  - This naturally avoids thundering herd on the lowest-latency backend while still preferring fast ones.
- If no healthy backends: reject new connections immediately with a metric bump (do NOT accept-then-close after a delay).

**Graceful shutdown:**
- `SIGTERM`/`SIGINT` → close listener, stop accepting new conns, wait up to `RELAY_SHUTDOWN_TIMEOUT` (default 30s) for in-flight conns to drain, then force-close and exit 0.
- While draining, `/healthz` returns `503`.

**Observability:**
- `/healthz` on `RELAY_METRICS_ADDR` (default `:8080`):
  - 200 if pool loaded (cached or fresh) AND at least one healthy backend AND not shutting down.
  - 503 otherwise, with a small JSON body: `{"ok":false,"reason":"no_healthy_backends"}`.
- `/metrics` on the same addr:
  - `relay_connections_accepted_total`
  - `relay_connections_active` (gauge)
  - `relay_connections_rejected_total{reason=...}` (`no_healthy_backends`, `dial_failed`, `shutting_down`)
  - `relay_bytes_total{direction=c2b|b2c}`
  - `relay_backend_up{backend_id}`
  - `relay_backend_latency_ms{backend_id}`
  - `relay_pool_generation` (gauge)
  - `relay_pool_refresh_failures_total`
  - `relay_dial_total{backend_id,result=ok|fail}`
- Logs: `log/slog` JSON to stdout. Fields: `ts`, `level`, `msg`, `client`, `backend_id`, `backend_addr`, `bytes_c2b`, `bytes_b2c`, `duration_ms`. One line per completed proxied connection at INFO; no per-packet logs.

## Environment variables (all strings)

| Variable | Default | Purpose |
|---|---|---|
| `RELAY_CONTROL_API_URL` | *(required)* | e.g. `https://control-api.internal` |
| `RELAY_CONTROL_API_TOKEN` | *(required)* | Bearer for pool endpoint |
| `RELAY_ENTRY_ID` | *(required)* | UUID of this entry node in control-api |
| `RELAY_LISTEN_ADDR` | `:443` | Client-facing TCP listener |
| `RELAY_METRICS_ADDR` | `:8080` | `/healthz` + `/metrics` HTTP listener |
| `RELAY_POOL_REFRESH_SEC` | `30` | Pool poll interval |
| `RELAY_POOL_STALE_MAX_SEC` | `300` | Max age of cached pool before relay marks unhealthy |
| `RELAY_HEALTH_INTERVAL` | `10s` | TCP health-check period |
| `RELAY_HEALTH_TIMEOUT` | `2s` | TCP health-check dial timeout |
| `RELAY_DIAL_TIMEOUT` | `3s` | Client-triggered dial timeout |
| `RELAY_DIAL_MAX_ATTEMPTS` | `3` | Backends to try per client connection |
| `RELAY_HALF_CLOSE_TIMEOUT` | `15s` | Drain period after one direction EOFs |
| `RELAY_SHUTDOWN_TIMEOUT` | `30s` | SIGTERM drain window |

## Repository layout

Create at repo root:

```
cmd/relay/main.go           — CLI entrypoint, signal handling, wiring
internal/config/config.go   — env parsing, defaults, validation
internal/pool/pool.go       — Pool struct: backends, health state, selection
internal/pool/client.go     — HTTP client polling /api/v1/entry/{id}/backends
internal/pool/health.go     — health-check loop
internal/proxy/proxy.go     — accept loop, per-conn proxy, graceful shutdown
internal/proxy/copy.go      — bidirectional copy with byte accounting
internal/metrics/metrics.go — prometheus registration + exposed vars
internal/logx/logx.go       — slog JSON handler factory
go.mod / go.sum
Dockerfile                  — multi-stage, final = distroless/static:nonroot
.dockerignore
Makefile                    — build, test, lint, docker targets
README.md                   — ops runbook, ENV table, metrics list
```

## Tests (required to merge)

### Unit tests
- `internal/pool`:
  - selection excludes `enabled=false`
  - selection excludes `healthy=false`
  - weighted-by-weight/latency distribution over 10k draws matches expected ratios ±5%
  - `generation` dedup: same generation doesn't re-log
  - pool cache TTL: after `RELAY_POOL_STALE_MAX_SEC` with no refresh, `Healthy()` returns false
- `internal/proxy`:
  - bidirectional copy transfers bytes in both directions (use `net.Pipe` or two `net.TCPListener` on `127.0.0.1:0`)
  - graceful shutdown closes listener and drains active conns within deadline
  - dial failure on first backend retries next candidate
- `internal/config`:
  - missing required env → fatal error with clear message
  - duration parsing accepts `10s`, `500ms`, etc.

### Integration test (`integration_test.go`, behind `//go:build integration`)
- Spin up 2 fake TCP echo backends on loopback.
- Start relay with a stubbed pool (no HTTP): backend A healthy, B healthy.
- Open 100 client conns in parallel, write random payloads, verify echoes match.
- Kill backend A mid-flight; new connections must land on B; verify in-flight conns to A are closed cleanly without crashing the relay.
- Assert metrics: `relay_backend_up{A}=0`, `relay_backend_up{B}=1`, `relay_connections_rejected_total{reason="dial_failed"}` stays bounded.

### Load test harness (`load/load_test.go`, `//go:build load`)
- 1000 concurrent connections, 10 MiB each, against a loopback echo backend.
- Assert: p99 forwarding latency overhead < 5ms over direct dial, RSS < 500 MB, no goroutine leaks.
- This target is for local validation, not CI.

## Dockerfile requirements

- Multi-stage. Builder: `golang:1.22-alpine`. Final: `gcr.io/distroless/static-debian12:nonroot`.
- `CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /relay ./cmd/relay`
- `USER nonroot:nonroot`
- `EXPOSE 443 8080`
- `ENTRYPOINT ["/relay"]`
- Final image `< 20 MB`.

## Helm chart (separate from control-api chart)

Directory `chart/` (at repo root alongside the Go code):

```
chart/
  Chart.yaml                 — name: relay, apiVersion: v2
  values.yaml
  templates/
    deployment.yaml          — hostNetwork: true, nodeSelector kind=entry, tolerations, readinessProbe /healthz on :8080, livenessProbe /healthz
    service.yaml             — ClusterIP :8080 for metrics only (client traffic uses hostNetwork :443)
    serviceaccount.yaml
    configmap.yaml           — non-secret env
    secret.yaml              — RELAY_CONTROL_API_TOKEN from external-secret or stringData
    servicemonitor.yaml      — scrape :8080/metrics (gated by .Values.monitoring.enabled)
    _helpers.tpl
```

Values to expose: `image.repository`, `image.tag`, `image.pullPolicy`, `entryId`, `controlApi.url`, `controlApi.tokenSecretRef`, `resources`, `nodeSelector`, `tolerations`, `monitoring.enabled`, `replicaCount` (usually 1 per entry node via nodeSelector).

Replica count is driven by `nodeSelector` + `hostNetwork` — one pod per labeled entry node. The chart uses a `DaemonSet` rather than `Deployment` so it automatically runs on every node with `kind=entry` label. Prefer DaemonSet over per-entry Helm releases.

## CI workflow

File: `.github/workflows/relay-build.yml`

Triggers: `push` to `main`/`dev`, `pull_request` to `main`/`dev`, manual `workflow_dispatch`.

Jobs:
1. `test` — `go vet`, `go test -race ./...`, `go test -tags=integration ./...`. Cache modules.
2. `build` (depends on test, main/dev only) — `docker buildx build --platform linux/amd64` → push to `harbor.lannister-dev.ru/vpn-service/relay:${GITHUB_SHA::7}` and `:dev` (or `:latest` on main). Harbor creds from GitHub secrets.
3. `helm-lint` — `helm lint ./chart`.
4. Optional `deploy-dev` (manual) — calls the same Vault/Swarm pattern the control-api repo uses; leave a TODO comment referencing the k3s target if the maintainer has not yet supplied it.

Do not embed production secrets. Use `VAULT_ROLE_ID` / `VAULT_SECRET_ID` from org secrets if the maintainer wires them up; otherwise keep deploy behind a comment block.

## README.md (for the relay repo)

Must include:
- Architecture diagram (ASCII is fine): client → relay:443 → backend:443.
- ENV table (copy from this prompt).
- Metrics table.
- Local dev: `make run` with a local fake pool server.
- Ops runbook: how to drain an entry node (scale DaemonSet to 0 on that node, verify metrics, remove `kind=entry` label), how to rotate `RELAY_CONTROL_API_TOKEN`.

## Definition of done

- [ ] `go test -race ./...` green.
- [ ] `go test -tags=integration ./...` green.
- [ ] Docker image builds reproducibly, final size < 20 MB (`docker images` shows it).
- [ ] `helm lint ./chart` clean, `helm template ./chart` renders without errors.
- [ ] `README.md` covers ENV, metrics, ops.
- [ ] CI workflow runs to completion on a fresh PR.
- [ ] Load test run locally shows `p99 overhead < 5 ms` and RSS `< 500 MB` at 1000 conns. Paste the numbers into the PR description.

## Work order

1. `go.mod`, `internal/config`, `cmd/relay/main.go` skeleton that only loads env and logs it.
2. `internal/pool` with a stubbed HTTP client (read from a local JSON file) + unit tests.
3. `internal/proxy` + unit tests with `net.Pipe`.
4. Real HTTP client in `internal/pool/client.go` + retry/backoff.
5. Health checker.
6. Metrics + `/healthz`.
7. Integration test with 2 fake backends.
8. Dockerfile.
9. Helm chart.
10. CI workflow.
11. Load test + README.

Ship step 1–3 first and open a draft PR so the Python side (which owns the `/api/v1/entry/{id}/backends` endpoint) can integrate against your stubbed client shape.

## Out of scope (do NOT touch)

- Anything in the Python control-api repo.
- Subscription/VLESS URI building (Python side handles this).
- User placements and plan logic (Python side).
- REALITY key management (already synced by node agents, identical across backends).
- mTLS between relay and backend (intentionally omitted — REALITY already encrypts the payload).
