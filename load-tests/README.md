# Load Tests

Starter `k6` scenario for the main public client flow.

## What To Run First

- `subscriptions.js` for public subscription refresh traffic

## Install

macOS:

```bash
brew install k6
```

Docker:

```bash
docker run --rm -i grafana/k6 run - < load-tests/subscriptions.js
```

## Local Run

Subscription endpoint:

```bash
BASE_URL=https://api.lannister-dev.ru \
SUBSCRIPTION_TOKEN=<subscription_token> \
HWID=test-device-1 \
k6 run load-tests/subscriptions.js
```

## Grafana Cloud k6

If you want to see the run in `https://lannister.grafana.net`, use Grafana Cloud k6.

```bash
export K6_CLOUD_TOKEN=<grafana_cloud_k6_token>
BASE_URL=https://api.lannister-dev.ru \
SUBSCRIPTION_TOKEN=<subscription_token> \
HWID=test-device-1 \
k6 cloud run load-tests/subscriptions.js
```

## What To Watch

- `http_req_duration`
- `p(95)` / `p(99)`
- `http_req_failed`
- API container CPU / memory
- PostgreSQL CPU / slow queries
- Redis latency
- NATS reconnects / lag

## Notes

- `subscriptions.js` uses `User-Agent: Happ/1.0` by default to match your main client path.
- `subscriptions.js` treats both `200` and `304` as healthy.
- Start with small loads, then increase `stages`.
- For realistic tests, use multiple tokens/users instead of a single hot key.
