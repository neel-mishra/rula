// SLO endpoint read load: 100 VUs hammering /slo/status for 2 minutes.
// Validates the aggregation query stays under p95 1.5s without erroring.

import http from 'k6/http';
import { check } from 'k6';

import { authHeaders, baseUrl, sharedThresholds, stagedRamp } from '../k6.config.js';
import { smokeHealth } from '../lib/seed.js';

export const options = {
  ...stagedRamp(100, 120),
  thresholds: sharedThresholds,
};

export function setup() {
  smokeHealth();
}

export default function () {
  const res = http.get(`${baseUrl}/slo/status?window_days=7`, {
    headers: authHeaders(),
    tags: { endpoint: 'slo' },
  });
  check(res, {
    'slo 200': (r) => r.status === 200,
    'has metrics': (r) => {
      try {
        return Array.isArray(JSON.parse(r.body).metrics);
      } catch (_) {
        return false;
      }
    },
  });
}
