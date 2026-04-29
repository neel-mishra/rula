// Webhook spike: Gmail Pub/Sub burst at the ingest webhook.
// Stages: baseline 10 RPS for 60s -> spike 200 RPS for 30s -> cooldown.
// Validates webhook intake stays under p95 2s with <1% errors.

import http from 'k6/http';
import { check } from 'k6';

import { baseUrl, sharedThresholds, webhookHeaders } from '../k6.config.js';
import { gmailPushEnvelope } from '../lib/payloads.js';
import { smokeHealth } from '../lib/seed.js';

export const options = {
  scenarios: {
    baseline: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 20,
      maxVUs: 50,
      exec: 'pushOne',
    },
    spike: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 200,
      maxVUs: 400,
      startTime: '60s',
      exec: 'pushOne',
    },
  },
  thresholds: sharedThresholds,
};

export function setup() {
  smokeHealth();
  return {};
}

export function pushOne() {
  const body = JSON.stringify(gmailPushEnvelope({}));
  const res = http.post(`${baseUrl}/webhooks/gmail`, body, {
    headers: webhookHeaders(),
    tags: { endpoint: 'webhook' },
  });
  check(res, {
    'webhook 2xx': (r) => r.status >= 200 && r.status < 300,
  });
}
