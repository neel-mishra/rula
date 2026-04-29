// Auth helpers for load tests.
// JWT is provided externally (see README); we do not mint HS256 in k6.

export function bearer(token) {
  return `Bearer ${token}`;
}

export function jsonAuth(token) {
  return {
    'Content-Type': 'application/json',
    Authorization: bearer(token),
  };
}

// Used by webhook-spike: Gmail Pub/Sub auth via the project's shared bearer
// secret (settings.gmail_webhook_secret). The HMAC fallback path is not
// exercised here — real Pub/Sub uses the bearer token in production.
export function pubsubAuth(secret) {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${secret}`,
  };
}

// Mint a fresh correlation id per request — useful for tracing in CloudWatch.
export function correlationId() {
  return `load-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}
