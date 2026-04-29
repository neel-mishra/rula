# MVP Sandbox Readiness Tickets (Critical Remaining)

Purpose: track the remaining must-do engineering work to run and validate the sandbox MVP with real integrations.

## MVP-READ-001 — OAuth Callback + Gmail Watch End-to-End Validation

- **Why it matters:** The MVP cannot ingest real inbox traffic unless Gmail OAuth callback and watch registration succeed against real Google credentials.
- **Scope (in):** Validate `/mailbox-connect/gmail/connect` and `/mailbox-connect/gmail/callback` flow, token exchange, label setup, and watch registration path in `api/routers/mailbox_connect.py`.
- **Scope (out):** OAuth consent screen product/legal copy changes and non-Gmail providers.
- **Implementation notes:** Use sandbox domain redirect URI already documented in `docs/sandbox-bringup.md`; add a repeatable validation checklist for success/failure states (invalid state, revoked token, missing webhook topic). Capture expected DB field updates (`gmail_watch_expiration`, `gmail_history_id`).
- **Acceptance criteria:** A test mailbox can be connected in sandbox UI, mailbox row is active/connected with non-empty watch metadata, and a failure case returns clear actionable error in API logs.
- **Owner suggestion:** backend
- **Priority:** P0

## MVP-READ-002 — Pub/Sub Webhook Auth + Payload Validation Hardening

- **Why it matters:** Sandbox signals are untrustworthy if webhook auth or payload verification is inconsistent with real Pub/Sub delivery behavior.
- **Scope (in):** Validate and harden `/webhooks/gmail` signature/token path in `api/routers/webhooks.py`, including auth header flow and fallback signature flow.
- **Scope (out):** Full webhook replay-prevention platform overhaul.
- **Implementation notes:** Confirm expected header contract from Google push configuration in `docs/sandbox-bringup.md`; add tests for accepted/rejected auth cases, malformed JSON, bad base64 payload, and unknown mailbox behavior.
- **Acceptance criteria:** Valid push request is accepted and dispatches ingest job; invalid token/signature is rejected with 403; malformed request returns 400 without crashing worker/API.
- **Owner suggestion:** backend
- **Priority:** P0

## MVP-READ-003 — Migration Bootstrap Gate for Fresh Sandbox Bring-up

- **Why it matters:** A fresh sandbox must reliably reach schema head before API/worker start, or QA results become non-deterministic.
- **Scope (in):** Verify and enforce migration bootstrap via `migrate` service (`alembic upgrade head`) in `docker-compose.prod.yml` plus `migrations/env.py` and `migrations/versions`.
- **Scope (out):** Historical migration refactor or squashing.
- **Implementation notes:** Add a preflight step that confirms migration head is reachable from clean volume state; document and test failure behavior if migration errors (API/worker should not start).
- **Acceptance criteria:** From empty Docker volumes, `docker compose -f docker-compose.prod.yml up -d` results in completed `migrate` and healthy `api`/`worker`; on forced migration failure, `api`/`worker` remain blocked.
- **Owner suggestion:** platform
- **Priority:** P0

## MVP-READ-004 — Production Compose Bring-up Verification Matrix

- **Why it matters:** MVP sandbox confidence requires repeatable evidence that the entire production-like stack can boot and stay healthy.
- **Scope (in):** Verify service health and dependency wiring for `caddy`, `api`, `worker`, `postgres`, `redis`, `frontend`, `jaeger`, `otel-collector`, `minio`, `pgbackup` in `docker-compose.prod.yml`.
- **Scope (out):** Non-sandbox cloud deployment automation.
- **Implementation notes:** Create a one-command verification matrix (container status, healthcheck status, critical endpoint checks, basic login/API reachability) and pin expected output patterns.
- **Acceptance criteria:** Bring-up checklist passes on a clean sandbox VM twice in a row; failures are mapped to explicit remediation actions in docs.
- **Owner suggestion:** platform
- **Priority:** P0

## MVP-READ-005 — Sandbox Smoke Runbook Execution + Evidence Capture

- **Why it matters:** Readiness is incomplete without a reproducible smoke path proving user-critical workflow from login to triage/draft.
- **Scope (in):** Convert current smoke section in `docs/sandbox-bringup.md` into an explicit executable runbook with evidence checkpoints.
- **Scope (out):** Full regression suite automation.
- **Implementation notes:** Add required artifacts per step (HTTP status, log snippet, DB snapshot, UI confirmation) for login, mailbox connect, webhook receipt, ingest processing, triage visibility, and draft creation.
- **Acceptance criteria:** A non-author operator can run the smoke runbook end-to-end in under 45 minutes and produce complete evidence bundle with no ambiguous steps.
- **Owner suggestion:** qa
- **Priority:** P0

## MVP-READ-006 — Observability Sanity Checks for API + Worker Paths

- **Why it matters:** Without trace and metric sanity, incidents cannot be diagnosed quickly during MVP QA.
- **Scope (in):** Validate tracing bootstrap from `core/observability/tracing.py`, OTEL collector wiring (`infra/otel-collector.yml`), and Jaeger visibility for API and worker flows.
- **Scope (out):** Long-term dashboard redesign.
- **Implementation notes:** Define minimum required spans/events for a smoke email lifecycle; verify both “tracing disabled” and “tracing enabled” modes behave as expected. Add quick checks to `docs/sandbox-bringup.md`.
- **Acceptance criteria:** Smoke flow emits visible end-to-end traces in Jaeger (HTTP ingress -> queue dispatch -> worker processing), and missing endpoint config is surfaced clearly in logs.
- **Owner suggestion:** platform
- **Priority:** P1

## MVP-READ-007 — Backup/Restore Drill for Postgres Data Path

- **Why it matters:** Sandbox readiness requires proof that MVP data can be restored from backups before launch gating.
- **Scope (in):** Validate backup artifact creation from `pgbackup` service in `docker-compose.prod.yml` and execute a documented restore drill into a clean Postgres instance.
- **Scope (out):** Cross-region backup strategy and object-storage archival.
- **Implementation notes:** Define a deterministic drill dataset (users/mailboxes/emails/drafts), run backup, wipe target DB, restore, and compare key row counts/integrity fields post-restore.
- **Acceptance criteria:** Restore drill succeeds within target window; restored dataset matches expected integrity checks; runbook location is linked from `docs/release-readiness.md` item 5.
- **Owner suggestion:** platform
- **Priority:** P0

## MVP-READ-008 — Gmail Watch Failure Runbook Alignment to Sandbox Reality

- **Why it matters:** Current watch-failure runbook references cloud components that may not match sandbox architecture, which can delay incident recovery.
- **Scope (in):** Reconcile `docs/runbooks/gmail-watch-failure.md` with actual sandbox stack/routes (`/webhooks/gmail`, compose services, local logs, manual backfill path).
- **Scope (out):** Full incident process rewrite.
- **Implementation notes:** Replace any environment-specific assumptions (Lambda/EventBridge-only steps) with dual-path guidance: sandbox-local and cloud-managed. Ensure SQL checks and webhook probe commands are valid for this repo.
- **Acceptance criteria:** On simulated watch expiration, an on-call engineer can follow the runbook to detect issue, re-register watch, backfill safely, and confirm recovery with concrete commands.
- **Owner suggestion:** qa
- **Priority:** P1
