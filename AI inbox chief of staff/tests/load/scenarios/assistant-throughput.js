// Assistant endpoint throughput: instructions in, rules/clarifications out.
// MANUAL / STAGING ONLY — hits live LLM. Set KILL_SWITCH_LLM=true in
// the API process to exercise the deterministic fallback at zero cost.

import http from 'k6/http';
import { check } from 'k6';

import { authHeaders, baseUrl, sharedThresholds } from '../k6.config.js';
import { assistantInstruction } from '../lib/payloads.js';
import { ensureMinMailboxes } from '../lib/seed.js';

export const options = {
  scenarios: {
    instructions: {
      executor: 'constant-arrival-rate',
      rate: 5,           // intentionally gentle — LLM-bound
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 20,
      maxVUs: 40,
    },
  },
  thresholds: {
    ...sharedThresholds,
    'http_req_duration{endpoint:assistant}': ['p(95)<8000'],
  },
};

export function setup() {
  return { mailboxIds: ensureMinMailboxes(1) };
}

export default function (data) {
  const mailboxId = data.mailboxIds[Math.floor(Math.random() * data.mailboxIds.length)];
  const body = JSON.stringify(assistantInstruction({ mailboxId }));
  const res = http.post(`${baseUrl}/assistant/instruction`, body, {
    headers: authHeaders(),
    tags: { endpoint: 'assistant' },
  });
  check(res, {
    'assistant 2xx': (r) => r.status < 300,
  });
}
