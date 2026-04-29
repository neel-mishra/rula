# Sandbox MVP Go-Live Checklist

Use this checklist to run final QA validation before declaring the sandbox MVP ready.

## Scope

This checklist validates:

- stack boot + migration gating
- auth + mailbox connect flow
- webhook ingest route behavior
- queue/worker activity signals
- observability visibility
- backup/restore drill readiness

It does not replace full production hardening or load testing.

## Preconditions

- Sandbox VM is provisioned with Docker + Compose.
- DNS and TLS are configured for your sandbox domain.
- `.env.prod` is populated (based on `.env.prod.example`) with real sandbox values.
- Gmail OAuth + Pub/Sub push are configured for the sandbox redirect URI:
  - `https://<your-domain>/mailbox-connect/gmail/callback`

## 1) Static preflight checks (local repo)

Run from repo root:

```bash
make verify-migration-gate
```

Pass criteria:

- Output contains:
  - `PASS: migration gate wiring is present`
  - `PASS: verified migration gate compose wiring`

Fail action:

- Fix `docker-compose.prod.yml` migration wiring before continuing.

## 2) Bring up stack

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

If your Compose implementation does not support `service_completed_successfully`:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrate
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

## 3) Compose matrix verification

```bash
make sandbox-matrix-check
```

Pass criteria:

- `api`, `worker`, `postgres`, `redis`, `frontend`, `caddy`, `jaeger`, `otel-collector`, `minio`, `pgbackup` are present and healthy/running as expected.
- API health endpoint check returns `200`.

Fail action:

- Follow remediation in `docs/sandbox-compose-verification.md`.

## 4) Day-0 smoke validation

Basic reachability:

```bash
make sandbox-smoke BASE_URL=https://<your-domain>
```

Auth-backed smoke (recommended):

```bash
make sandbox-smoke \
  BASE_URL=https://<your-domain> \
  SMOKE_EMAIL=qa+smoke@<your-domain> \
  SMOKE_PASSWORD='<strong-password>' \
  SAVE_EVIDENCE=1
```

Optional explicit evidence location:

```bash
BASE_URL=https://<your-domain> \
SMOKE_EMAIL=qa+smoke@<your-domain> \
SMOKE_PASSWORD='<strong-password>' \
SAVE_EVIDENCE=1 \
EVIDENCE_DIR=artifacts/sandbox-go-live-$(date +%Y%m%d-%H%M%S) \
./scripts/sandbox_smoke.sh
```

Pass criteria:

- Script exits 0.
- Outputs all required `PASS:` checks.
- Evidence bundle (if enabled) contains:
  - `endpoint-status-summary.tsv`
  - `responses/`
  - `command-env-metadata.txt`
  - `README.txt`

## 5) Manual product flow verification

1. Open `https://<your-domain>/login`
2. Register/sign in
3. Connect Gmail mailbox
4. Send test email to connected mailbox
5. Confirm:
   - webhook accepted at `/webhooks/gmail`
   - worker processes ingest
   - triage appears in UI
   - draft generated for actionable message

Evidence to capture:

- Screenshot/video for each step
- API/worker log snippet with correlation ids
- Mailbox row shows connected/watch metadata

## 6) Observability sanity

```bash
make observability-sanity \
  BASE_URL=https://<your-domain> \
  JAEGER_URL=http://<vm-ip>:16686
```

Pass criteria:

- OTEL endpoint visibility checks pass.
- Jaeger endpoint reachable.
- API health reachable.
- At least one trace appears in Jaeger after smoke traffic.

## 7) Backup/restore drill (dry run then real)

Dry run:

```bash
./scripts/backup_restore_drill.sh
```

Real run:

```bash
RUN=1 ./scripts/backup_restore_drill.sh
```

Pass criteria:

- Script reports successful row-count parity across core tables.
- Drill artifacts are saved and reviewable.

## 8) Final QA sign-off template

Mark each item:

- [ ] Migration gate verified
- [ ] Compose matrix check passed
- [ ] Smoke script passed
- [ ] Auth-backed smoke passed
- [ ] Manual mailbox connect + ingest + triage + draft validated
- [ ] Observability sanity passed
- [ ] Backup/restore drill passed
- [ ] Evidence bundle archived

Decision:

- **GO** if all checks pass.
- **NO-GO** if any P0 check fails.
