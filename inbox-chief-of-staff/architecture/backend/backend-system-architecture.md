# Backend System Architecture — Inbox Chief of Staff (Prototype / Phase 1)

## Overview

The backend is a Python-based pipeline that receives Gmail events, runs them through AI agents (triage, draft, brief), and surfaces structured outputs to a review UI. It is designed for a single-tenant prototype first; the data model and service boundaries are drawn so that multi-tenant SaaS can be layered on later without rewrites.

---

## Technology Stack

| Concern | Choice | Notes |
|---|---|---|
| API server | FastAPI (Python 3.12) | Async endpoints, OpenAPI docs auto-generated |
| Background workers | Celery workers OR Cloud Tasks handlers | Cloud Tasks preferred for serverless-first; Celery available as fallback for local dev |
| Relational DB | Cloud SQL Postgres 15 | Managed, IAM auth, automatic backups |
| Vector store | pgvector extension on same Postgres instance | Avoids a second datastore in prototype |
| Migrations | Alembic | Version-controlled, CI-gated |
| Object storage | GCS | Raw message payloads, log bundles, eval artifact dumps |
| Secrets | Google Secret Manager | KMS-wrapped key for token encryption |
| Deployment | Cloud Run (two services: api, worker) | Scales to zero; no idle cost |

---

## Service Layout

```
inbox-chief-of-staff/
├── api/                        # HTTP surface
│   ├── routers/
│   │   ├── auth.py             # OAuth 2.0 endpoints (Google login, token exchange)
│   │   ├── messages.py         # List / get normalized messages
│   │   ├── drafts.py           # Review, accept, reject, edit drafts
│   │   ├── briefs.py           # Fetch morning / afternoon brief
│   │   ├── webhooks.py         # Receive Gmail push notifications (Pub/Sub HTTP push)
│   │   └── health.py           # Liveness + readiness probes
│   └── main.py                 # FastAPI app factory, middleware, lifespan hooks
│
├── ingestion/
│   ├── oauth_flow.py           # Gmail OAuth consent → refresh token storage
│   ├── webhook_handler.py      # Decode Pub/Sub envelope, validate HMAC, enqueue task
│   ├── gmail_client.py         # Thin wrapper over Google Gmail API (messages.get, watch)
│   └── normalizer.py           # Raw Gmail payload → normalized Message domain object
│
├── orchestrator/
│   ├── state_machine.py        # Defines states + valid transitions; owns all DB writes
│   ├── dispatcher.py           # Decides which agent(s) to invoke based on triage output
│   └── workflow_runner.py      # Top-level task entry point invoked by worker
│
├── agents/
│   ├── base_agent.py           # LLM wrapper: calls Claude API, handles retries, emits telemetry
│   ├── triage_agent.py         # Classifies message priority; falls back to rule engine
│   ├── draft_agent.py          # Generates reply draft; always sets draft_only=True
│   └── brief_agent.py          # Summarizes a batch of messages into a digest
│
├── policy/
│   └── action_policy.py        # Allowlist enforcer; raises PolicyViolationError on blocked actions
│
├── repositories/               # All DB access lives here; agents never import this directly
│   ├── message_repo.py
│   ├── workflow_repo.py
│   ├── draft_repo.py
│   └── audit_repo.py
│
├── telemetry/
│   ├── event_emitter.py        # Structured event logging (Cloud Logging + local stdout)
│   └── eval_harness.py         # Persists eval_samples rows for offline scoring
│
├── db/
│   ├── models.py               # SQLAlchemy ORM models
│   └── migrations/             # Alembic env + version files
│
└── core/
    ├── config.py               # Pydantic Settings (env vars, Secret Manager integration)
    └── exceptions.py           # PolicyViolationError, OrchestratorError, etc.
```

---

## Data Flow Narrative

### Step 1 — Gmail Webhook Arrival

Gmail sends a Pub/Sub HTTP push notification to `POST /webhooks/gmail`. The `webhook_handler` in `ingestion/` validates the Pub/Sub HMAC signature, decodes the base64 message data (which contains the Gmail `historyId` and mailbox address), and immediately enqueues a Cloud Tasks task (`ingest_message`) with the relevant identifiers. The HTTP response is returned in under 200 ms so Gmail does not retry.

### Step 2 — Message Ingestion

The Cloud Tasks worker picks up `ingest_message`. `gmail_client.py` calls `messages.get` with `format=full` to retrieve the raw payload. The raw JSON is written to GCS (`gs://{bucket}/raw/{user_id}/{message_id}.json`) and a `messages` row is created with `ingest_status=INGESTED`.

### Step 3 — Normalization

`normalizer.py` extracts subject, sender, body preview (500 chars stripped of HTML), thread ID, and received timestamp from the raw payload. It updates the `messages` row with the parsed fields and advances `ingest_status` to `NORMALIZED`. A `workflow_runs` row is created in state `NORMALIZED`.

### Step 4 — Orchestrator Entry

`workflow_runner.py` is invoked (either inline or as a second Cloud Tasks task). `state_machine.py` transitions the workflow to `TRIAGED` only after the triage agent completes and returns a result above the confidence threshold.

### Step 5 — Triage Agent Dispatch

`dispatcher.py` calls `triage_agent.py` with a `TriageInput`. The agent calls the LLM (Claude claude-sonnet-4-6), receives a `TriageOutput`. If `confidence < 0.70` the agent falls back to a deterministic rule: sender-domain allowlist + keyword scan. `base_agent.py` emits a telemetry event immediately after the LLM call, regardless of outcome.

### Step 6 — Downstream Dispatch

Based on `TriageOutput.priority`:
- `urgent` or `normal` → enqueue `generate_draft` task → `DRAFT_QUEUED`
- `brief` → accumulated for next brief window → `BRIEF_QUEUED`
- `archive` → workflow transitions directly to `COMPLETED` with no further agent work
- Any thread flagged with follow-up keywords → `FOLLOW_UP_FLAGGED` (can co-occur)

### Step 7 — Policy Check (every agent action)

Before any Gmail API write (draft creation, label application), `action_policy.py` is called with the proposed action enum. Allowed actions (`WRITE_DRAFT`, `ADD_LABEL`, `READ_MESSAGE`) pass through. Any blocked action (`SEND_EMAIL`, `DELETE_MESSAGE`, `ARCHIVE_MESSAGE`, `MODIFY_CONTACTS`) raises `PolicyViolationError`, writes an `audit_events` row with `outcome=BLOCKED`, and halts the workflow run, setting its state to `REJECTED`.

### Step 8 — Action Execution

`draft_agent.py` calls the Gmail Drafts API to persist the draft. The `drafts` table row is created with `status=pending`. The workflow transitions to `PENDING_REVIEW`.

### Step 9 — User Review UI Response

The front-end polls (or receives a push event) for `workflow_runs` in state `PENDING_REVIEW`. The user sees the draft, can accept, reject, or edit it. On acceptance the workflow transitions to `COMPLETED`; on rejection, to `REJECTED`. User feedback is stored in `drafts.user_feedback`.

---

## Key Invariants

1. **Policy guard is mandatory.** Every proposed Gmail API write is passed through `action_policy.py`. There is no bypass path. Agents do not call Gmail directly.

2. **Orchestrator owns all state transitions.** Only `state_machine.py` calls `workflow_repo.update_state()`. Agents return plain data objects; they never touch the database.

3. **Agents are stateless.** An agent function receives an input struct and returns an output struct. It holds no session state, no DB connections, and no in-process caches.

4. **Every agent call emits a telemetry event.** `base_agent.py` wraps all LLM calls and unconditionally emits an event containing: `input_hash` (SHA-256 of serialized input), `output_hash`, `confidence`, `model_version`, `latency_ms`, `workflow_run_id`. This feeds the eval harness.

5. **Repository pattern for all DB access.** Agent code imports only input/output types. Repository classes in `repositories/` are injected by the orchestrator. This makes agents fully unit-testable without a database.

---

## Deployment Target (Prototype)

```
Google Cloud Project: rula-inbox-prototype
Region: us-central1

Services
├── cloud-run/api              # FastAPI app; min-instances=1 to avoid cold-start on webhooks
├── cloud-run/worker           # Celery worker OR Cloud Tasks HTTP target
│
Infrastructure
├── cloud-sql/postgres-15      # db-g1-small for prototype; pgvector enabled
├── cloud-tasks/inbox-queue    # Default queue; max 10 concurrent dispatches
├── gcs/rula-inbox-artifacts   # Raw payloads, log bundles, eval dumps
├── secret-manager             # GOOGLE_CLIENT_SECRET, KMS_KEY_NAME, DATABASE_URL
└── pubsub/gmail-notifications # Gmail watch target → Cloud Run /webhooks/gmail
```

### Cloud Run configuration notes

- API service requires `--allow-unauthenticated` only on `/webhooks/gmail` (validated by HMAC); all other routes require a bearer token.
- Worker service is internal-only (`--ingress=internal`); only Cloud Tasks can reach it.
- Both services use Workload Identity to access Cloud SQL, GCS, and Secret Manager — no service account key files.

### Environment variable surface

| Variable | Source |
|---|---|
| `DATABASE_URL` | Secret Manager |
| `GCS_BUCKET` | Cloud Run env |
| `CLOUD_TASKS_QUEUE` | Cloud Run env |
| `ANTHROPIC_API_KEY` | Secret Manager |
| `GOOGLE_CLIENT_ID` | Secret Manager |
| `GOOGLE_CLIENT_SECRET` | Secret Manager |
| `KMS_KEY_NAME` | Cloud Run env |
| `PUBSUB_AUDIENCE` | Cloud Run env (for webhook OIDC validation) |

---

## Local Development

```bash
# Spin up Postgres + pgvector locally
docker compose up -d db

# Apply migrations
alembic upgrade head

# Run API
uvicorn api.main:app --reload

# Run worker (Celery mode)
celery -A orchestrator.workflow_runner worker --loglevel=info

# Run worker (Cloud Tasks emulator mode)
functions-framework --target=cloud_tasks_handler --port=8081
```

`docker-compose.yml` provides: `postgres:15-pgvector`, `redis:7` (for Celery broker in local mode), and a stub Pub/Sub emulator.
