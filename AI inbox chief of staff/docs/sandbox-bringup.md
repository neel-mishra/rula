# Sandbox Bring-up (Phase 4c)

This runbook brings up a single-VM sandbox stack for MVP QA using:

- `docker-compose.prod.yml`
- `Caddyfile` for TLS + routing
- local Postgres/Redis/MinIO/Jaeger/OTel
- external Gmail OAuth + Anthropic + optional Slack

## 1) Provision VM + DNS

- Provision Hetzner CX32 (or CX22 fallback).
- Install Docker Engine + Compose plugin.
- Point an A record for your domain (for example `sandbox.example.com`) to the VM IP.
- Open inbound ports `80` and `443`.

## 2) Prepare repo + env file

- Clone this repo on the VM.
- Copy `.env.prod.example` to `.env.prod`.
- Fill `.env.prod` with real values for:
  - Gmail OAuth and webhook config
  - Anthropic key
  - app secret + token encryption key
  - Postgres/Redis/MinIO credentials
  - domain/Caddy vars

## 3) Generate local secrets

Recommended commands:

- `openssl rand -hex 32` for `APP_SECRET_KEY`
- `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` for `TOKEN_ENCRYPTION_KEY`
- `openssl rand -hex 24` for `POSTGRES_PASSWORD`
- `openssl rand -hex 24` for `REDIS_PASSWORD`
- `openssl rand -hex 16` for `MINIO_ROOT_USER`
- `openssl rand -hex 24` for `MINIO_ROOT_PASSWORD`

## 4) Configure Google OAuth + Gmail push

- In Google Cloud, configure OAuth consent screen + OAuth client.
- Set redirect URI to:
  - `https://<your-domain>/mailbox-connect/gmail/callback`
- Create Pub/Sub topic and set:
  - `GMAIL_WEBHOOK_TOPIC=projects/<project>/topics/<topic>`
- Set `GMAIL_WEBHOOK_SECRET` and configure push auth token/header accordingly.

## 5) Build, migrate, and launch stack

From repo root:

- `chmod +x scripts/verify_migration_gate.sh` (one-time per checkout if needed)
- `./scripts/verify_migration_gate.sh`
- `docker compose -f docker-compose.prod.yml --env-file .env.prod build`
- `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`

The production compose includes a one-shot `migrate` service that runs `alembic upgrade head` against the compose `postgres` service. `api` and `worker` are configured to wait for successful migration completion before starting.

Expected migration output includes Alembic lines similar to:

- `INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.`
- `INFO  [alembic.runtime.migration] Running upgrade ... -> ...`

If startup fails, explicitly inspect migration status before debugging API/worker:

- `docker compose -f docker-compose.prod.yml --env-file .env.prod ps migrate`
- `docker compose -f docker-compose.prod.yml --env-file .env.prod logs --no-color migrate`

Expected terminal state:

- `migrate` exits with code `0`.
- `api` and `worker` remain blocked until migration completes successfully.
- Any migration failure is surfaced by non-zero `migrate` exit status and Alembic traceback in logs.

If your Docker Compose version does not support `depends_on.condition: service_completed_successfully`, run migrations explicitly before `up`:

- `docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrate`
- `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`

Optional status checks:

- `docker compose -f docker-compose.prod.yml ps`
- `docker compose -f docker-compose.prod.yml logs -f api`
- `docker compose -f docker-compose.prod.yml logs -f caddy`

## 6) Run Day-0 smoke validation

From repo root:

- `chmod +x scripts/sandbox_smoke.sh` (one-time per checkout if needed)
- `BASE_URL="https://<your-domain>" ./scripts/sandbox_smoke.sh`

Optional auth-backed probe (register/login + mailbox connect with token):

- `BASE_URL="https://<your-domain>" SMOKE_EMAIL="qa+smoke@<your-domain>" SMOKE_PASSWORD="<strong-password>" ./scripts/sandbox_smoke.sh`

Evidence capture (recommended for runbook audit trail):

- `BASE_URL="https://<your-domain>" SAVE_EVIDENCE=1 ./scripts/sandbox_smoke.sh`
- `BASE_URL="https://<your-domain>" SAVE_EVIDENCE=1 EVIDENCE_DIR="./artifacts/day0-smoke-$(date -u +%Y%m%dT%H%M%SZ)" ./scripts/sandbox_smoke.sh`

When `SAVE_EVIDENCE=1`, the script writes an evidence bundle to:

- `EVIDENCE_DIR` if provided
- otherwise `./artifacts/smoke-evidence-<timestamp>`

Expected artifact files:

- `README.txt` (bundle manifest)
- `endpoint-status-summary.tsv` (check/method/url/status/result)
- `command-env-metadata.txt` (runtime metadata with sensitive values redacted)
- `responses/*.txt` (one response snippet per smoke check)

Equivalent Make target:

- `make sandbox-smoke BASE_URL=https://<your-domain>`
- `make sandbox-smoke BASE_URL=https://<your-domain> SMOKE_EMAIL=qa+smoke@<your-domain> SMOKE_PASSWORD='<strong-password>'`

Pass/fail interpretation:

- Script is **fail-fast**: first unexpected response exits non-zero with `FAIL: ...` and includes status/body context.
- `PASS` means endpoint is reachable with expected semantics:
  - `/health/` must return `200`.
  - `/auth/register` and `/auth/login` may return validation/auth statuses when probing reachability.
  - `/mailbox-connect/gmail/connect` may return `401/403/422` if unauthenticated (still considered reachable).
  - `/webhooks/gmail` (optional check) accepts route-level statuses (`200/202/400/401/403/422`).
- `404`/`405` on webhook probe indicates probable route wiring issue and fails.

After script passes, continue with manual QA flow:

1. Open `https://<your-domain>/login`
2. Register account + sign in
3. Connect Gmail mailbox from dashboard
4. Send a test email into connected mailbox
5. Verify:
   - webhook accepted at `/webhooks/gmail`
   - ingest worker processes queue
   - triage decision appears in UI
   - draft record is created for actionable mail

## 7) Observability + backup verification

- Open Jaeger UI: `http://<vm-ip>:16686` and confirm traces.
- Open MinIO console: `http://<vm-ip>:9001` and verify bucket/object activity.
- Confirm daily backup container is healthy (`pgbackup` service logs).

### Observability sanity checklist (API + worker traces)

Run the script from repo root:

- `chmod +x scripts/observability_sanity.sh` (one-time per checkout if needed)
- `BASE_URL="https://<your-domain>" JAEGER_URL="http://<vm-ip>:16686" ./scripts/observability_sanity.sh`

Equivalent Make target:

- `make observability-sanity BASE_URL=https://<your-domain> JAEGER_URL=http://<vm-ip>:16686`

What it validates:

1. `OTEL_EXPORTER_OTLP_ENDPOINT` visibility from at least one source:
   - current shell env, and/or
   - `.env.prod`, and/or
   - running `api` / `worker` containers in compose.
2. Jaeger UI is reachable when `EXPECT_JAEGER=1` (default).
3. API health route is reachable (`/health/` returns `200`).
4. Provides follow-up commands for quick trace generation + Jaeger inspection.

Useful toggles:

- `EXPECT_JAEGER=0` to skip Jaeger reachability check.
- `ENV_FILE=.env.staging` to inspect a different env file.
- `COMPOSE_FILE=docker-compose.dev.yml` for dev-stack container probes.
- Run the deterministic backup/restore drill runbook: `docs/backup-restore-drill.md`
  - `chmod +x scripts/backup_restore_drill.sh`
  - `RUN=1 ./scripts/backup_restore_drill.sh`

## Troubleshooting quick checks

- **TLS not issuing**: verify DNS A record points to VM and ports `80/443` are open.
- **OAuth callback mismatch**: check exact redirect URI in Google console and `.env.prod`.
- **Queue inactivity**: check `QUEUE_BACKEND` and Redis connectivity from `worker`.
- **No drafts**: inspect `api` + `worker` logs for mailbox auth errors and LLM failures.
