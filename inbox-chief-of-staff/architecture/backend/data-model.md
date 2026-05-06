# Data Model — Inbox Chief of Staff

## Overview

All relational state lives in a single Cloud SQL Postgres 15 instance with the `pgvector` extension enabled. Alembic manages migrations. The schema is designed for a single-user prototype but uses `user_id` foreign keys throughout so multi-tenant isolation can be introduced without structural changes.

---

## Tables

### `users`

Stores one row per registered user. The `google_refresh_token` is **never** stored in plaintext — see the encryption note at the bottom of this document.

```sql
CREATE TABLE users (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                TEXT NOT NULL UNIQUE,
    google_refresh_token TEXT,            -- encrypted at app layer; see encryption notes
    timezone             TEXT NOT NULL DEFAULT 'UTC',  -- IANA tz string
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

### `mailbox_connections`

One row per Gmail address linked to a user account. A user may eventually link multiple addresses; the prototype assumes one.

```sql
CREATE TABLE mailbox_connections (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gmail_address    TEXT NOT NULL,
    watch_expiry     TIMESTAMPTZ,         -- Gmail push watch renews every 7 days
    last_synced_at   TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'paused', 'disconnected')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, gmail_address)
);
```

---

### `messages`

One row per Gmail message that has been ingested. Raw payload is stored in GCS; only indexed fields live here.

```sql
CREATE TABLE messages (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gmail_message_id     TEXT NOT NULL,
    gmail_thread_id      TEXT NOT NULL,
    subject              TEXT,
    sender_email         TEXT,
    sender_name          TEXT,
    received_at          TIMESTAMPTZ,
    body_preview         TEXT,            -- first 500 chars, HTML stripped
    raw_payload_gcs_path TEXT,            -- gs://bucket/raw/{user_id}/{gmail_message_id}.json
    ingest_status        TEXT NOT NULL DEFAULT 'ingested'
                             CHECK (ingest_status IN ('ingested', 'normalized', 'failed')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, gmail_message_id)
);
```

---

### `workflow_runs`

Tracks the lifecycle of a single message through the pipeline. One workflow run per message (1:1 for prototype; drafts and briefs have their own tables).

```sql
CREATE TYPE workflow_state AS ENUM (
    'INGESTED',
    'NORMALIZED',
    'TRIAGED',
    'DRAFT_QUEUED',
    'BRIEF_QUEUED',
    'FOLLOW_UP_FLAGGED',
    'PENDING_REVIEW',
    'COMPLETED',
    'REJECTED'
);

CREATE TABLE workflow_runs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id     UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    state          workflow_state NOT NULL DEFAULT 'INGESTED',
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ,
    error_message  TEXT
);
```

---

### `triage_results`

One row per triage agent execution. Multiple rows can exist if the agent is retried (each attempt is recorded separately; the orchestrator uses the most recent non-errored row).

```sql
CREATE TABLE triage_results (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id  UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    priority         TEXT NOT NULL CHECK (priority IN ('urgent', 'normal', 'brief', 'archive')),
    confidence       NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    rationale        TEXT,
    labels           JSONB NOT NULL DEFAULT '[]',   -- list of Gmail label names
    fallback_used    BOOLEAN NOT NULL DEFAULT FALSE,
    model_version    TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

### `drafts`

Stores the AI-generated draft and tracks user review outcome. `gmail_draft_id` is populated once the draft is written to Gmail via the API.

```sql
CREATE TYPE draft_status AS ENUM ('pending', 'accepted', 'rejected', 'edited');

CREATE TABLE drafts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id  UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    gmail_draft_id   TEXT,                -- null until WRITE_DRAFT action completes
    body             TEXT NOT NULL,
    subject_line     TEXT NOT NULL,
    confidence       NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    status           draft_status NOT NULL DEFAULT 'pending',
    user_feedback    TEXT,                -- free-text note when user rejects or edits
    model_version    TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at      TIMESTAMPTZ
);
```

---

### `briefs`

One row per generated brief digest. `message_ids` and `action_items` are stored as JSONB arrays.

```sql
CREATE TABLE briefs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    time_window      TEXT NOT NULL CHECK (time_window IN ('morning', 'afternoon')),
    summary_markdown TEXT NOT NULL,
    action_items     JSONB NOT NULL DEFAULT '[]',   -- list of strings
    message_ids      JSONB NOT NULL DEFAULT '[]',   -- list of internal message UUIDs
    skipped_count    INTEGER NOT NULL DEFAULT 0,
    model_version    TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

### `audit_events`

Append-only log. Never updated after insert. Captures all policy checks, agent executions, and user actions.

```sql
CREATE TABLE audit_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workflow_run_id  UUID REFERENCES workflow_runs(id) ON DELETE SET NULL,
    event_type       TEXT NOT NULL,  -- e.g. ACTION_EXECUTED, POLICY_VIOLATION, USER_ACCEPTED
    agent_name       TEXT,           -- null for user-initiated events
    action           TEXT,           -- ActionEnum value, e.g. WRITE_DRAFT, SEND_EMAIL
    outcome          TEXT NOT NULL CHECK (outcome IN ('ALLOWED', 'BLOCKED', 'ERROR', 'SUCCESS')),
    metadata         JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

### `eval_samples`

Stores one row per agent invocation for offline evaluation. Input and output are referenced by hash; the full payloads are stored in GCS at `gs://bucket/eval/{sample_type}/{input_hash}.json`.

```sql
CREATE TYPE eval_sample_type AS ENUM ('triage', 'draft', 'brief');

CREATE TABLE eval_samples (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_type   eval_sample_type NOT NULL,
    input_hash    TEXT NOT NULL,            -- SHA-256 hex of serialized agent input
    output_hash   TEXT NOT NULL,            -- SHA-256 hex of serialized agent output
    human_label   TEXT,                     -- null until a human annotator scores it
    model_output  JSONB NOT NULL DEFAULT '{}',  -- agent output at time of capture
    score         NUMERIC(4,3),             -- null until eval pipeline scores it
    model_version TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## pgvector Table

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE message_embeddings (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id     UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    embedding      vector(1536) NOT NULL,   -- text-embedding-3-small output
    model_version  TEXT NOT NULL,           -- e.g. "text-embedding-3-small-v1"
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (message_id, model_version)      -- re-embed on model upgrade; keep old row
);
```

Embeddings are used by `brief_agent` to cluster related messages and by a future semantic search feature. The `1536` dimension matches OpenAI `text-embedding-3-small`; swap to `3072` if upgrading to `text-embedding-3-large`.

---

## Indexes

```sql
-- Fetch all messages for a user ordered by time (primary inbox query)
CREATE INDEX idx_messages_user_received
    ON messages (user_id, received_at DESC);

-- Look up the workflow run for a given message (1:1 in prototype)
CREATE INDEX idx_workflow_runs_message_id
    ON workflow_runs (message_id);

-- Audit log queries filtered by user and time range
CREATE INDEX idx_audit_events_user_created
    ON audit_events (user_id, created_at DESC);

-- Filter triage results by priority across a user's messages
CREATE INDEX idx_triage_results_priority
    ON triage_results (priority);

-- Pending review queue per user
CREATE INDEX idx_workflow_runs_user_state
    ON workflow_runs (user_id, state)
    WHERE state = 'PENDING_REVIEW';

-- ANN vector search on embeddings
CREATE INDEX idx_message_embeddings_ann
    ON message_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

---

## Encryption Notes

### `users.google_refresh_token`

Google OAuth refresh tokens grant long-lived access to a user's Gmail account. They must never be stored as plaintext.

**Encryption scheme (app-layer):**

1. At write time, `core/crypto.py` retrieves a 256-bit data encryption key (DEK) from **Google Cloud KMS** (a key stored in a dedicated KMS key ring, not in application config).
2. The DEK is used with **AES-256-GCM** to encrypt the token. The resulting ciphertext includes the GCM authentication tag and a random IV.
3. The encoded ciphertext (`base64(iv || ciphertext || tag)`) is stored in `google_refresh_token`.
4. At read time, the same KMS key is used to decrypt. If the KMS call fails, the token is treated as unavailable and the user is prompted to re-authenticate.

**KMS key rotation:** GCP KMS supports automatic key version rotation. Old versions are kept for decryption of existing tokens; new encryptions always use the current primary version.

**What is NOT done:**
- The refresh token is never logged.
- The refresh token is never included in telemetry events or `metadata` JSONB fields.
- The raw token is never returned by any API endpoint.

### Other sensitive fields

- `body_preview` in `messages` is not encrypted at the app layer (it is protected by Cloud SQL's default encryption at rest). In a production version, consider field-level encryption for PII.
- GCS objects (raw payloads) use default GCS encryption (Google-managed keys). A future version should use customer-managed encryption keys (CMEK) for the raw payload bucket.

---

## Migration Strategy

Alembic is the sole migration tool. Rules:

1. Every schema change ships as an Alembic revision file in `db/migrations/versions/`.
2. CI runs `alembic upgrade head` against a test database on every PR; the PR cannot merge if migrations fail.
3. Destructive migrations (column drop, type change) require a two-phase approach: deprecation phase (keep old column, add new column) followed by removal phase in the next release.
4. The `eval_samples` and `audit_events` tables are append-only by convention; no `UPDATE` or `DELETE` is issued against them by application code.
