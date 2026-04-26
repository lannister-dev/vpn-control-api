import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const SUBSCRIPTION_TOKEN = __ENV.SUBSCRIPTION_TOKEN || '';
const HWID = __ENV.HWID || 'k6-hwid-1';
const USER_AGENT = __ENV.USER_AGENT || 'Happ/1.0';
const THINK_TIME_SEC = Number(__ENV.THINK_TIME_SEC || '1');

if (!SUBSCRIPTION_TOKEN) {
  throw new Error('SUBSCRIPTION_TOKEN is required');
}

export const options = {
  scenarios: {
    subscription_refresh: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '1m', target: 20 },
        { duration: '3m', target: 50 },
        { duration: '1m', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const url = `${BASE_URL}/api/v1/subscriptions/sub/${SUBSCRIPTION_TOKEN}`;
  const response = http.get(url, {
    headers: {
      'User-Agent': USER_AGENT,
      'x-hwid': HWID,
    },
    tags: {
      endpoint: 'subscriptions_sub',
    },
  });

  check(response, {
    'subscription status is 200 or 304': (r) => r.status === 200 || r.status === 304,
    'subscription body or cache hit present': (r) => r.status === 304 || r.body.length > 0,
  });

  sleep(THINK_TIME_SEC);
}
