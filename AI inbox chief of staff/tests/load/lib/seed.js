// Seed helpers — confirm the env is ready before running scenarios.
// Mailbox creation is not automated here (requires OAuth); we verify
// that the operator has wired up at least N mailboxes for LOAD_TEST_JWT.

import http from 'k6/http';
import { check } from 'k6';

import { baseUrl, jwt } from '../k6.config.js';
import { jsonAuth } from './auth.js';

export function listMailboxes() {
  const res = http.get(`${baseUrl}/mailboxes`, { headers: jsonAuth(jwt) });
  if (res.status !== 200) {
    throw new Error(
      `Cannot list mailboxes (status ${res.status}). ` +
      'Confirm LOAD_TEST_JWT is valid and dev API is up.'
    );
  }
  const body = JSON.parse(res.body);
  return body.mailboxes || body || [];
}

export function ensureMinMailboxes(min) {
  const mailboxes = listMailboxes();
  if (mailboxes.length < min) {
    throw new Error(
      `Need at least ${min} connected mailboxes for this scenario; ` +
      `found ${mailboxes.length}. See README §"Seed test mailboxes".`
    );
  }
  return mailboxes.map((m) => m.id);
}

export function smokeHealth() {
  const res = http.get(`${baseUrl}/health/`);
  check(res, { 'health 200': (r) => r.status === 200 });
}
