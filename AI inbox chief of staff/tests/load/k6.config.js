// Shared k6 options + thresholds.
// Thresholds are aligned to core/slo/targets.py (see README §"What we're validating").

export const baseUrl = __ENV.LOAD_API_BASE || 'http://localhost:8000';
export const webhookSecret = __ENV.GMAIL_WEBHOOK_SECRET || 'dev-secret';
export const jwt = __ENV.LOAD_TEST_JWT || '';

// SLO thresholds — keep in lockstep with core/slo/targets.py.
// ingest_to_triage_p95 = 60000ms (60s) — observed indirectly via SLO endpoint.
// draft_generation_p95 = 45000ms (45s).
// Webhook intake should be sub-2s p95 (lighter than the full triage path).
export const sharedThresholds = {
  http_req_failed: ['rate<0.01'],
  'http_req_duration{endpoint:webhook}': ['p(95)<2000', 'p(99)<5000'],
  'http_req_duration{endpoint:slo}': ['p(95)<1500'],
  'http_req_duration{endpoint:assistant}': ['p(95)<8000'],
};

export function authHeaders() {
  if (!jwt) {
    throw new Error(
      'LOAD_TEST_JWT not set. See tests/load/README.md §"Mint a load-test JWT".'
    );
  }
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${jwt}`,
  };
}

export function webhookHeaders() {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${webhookSecret}`,
  };
}

export const stagedRamp = (peakVUs, sustainSec) => ({
  stages: [
    { duration: '15s', target: Math.floor(peakVUs / 4) },
    { duration: '30s', target: peakVUs },
    { duration: `${sustainSec}s`, target: peakVUs },
    { duration: '15s', target: 0 },
  ],
});
