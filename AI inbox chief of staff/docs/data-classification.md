# Data Classification Policy

**Status**: Draft v1
**Last updated**: 2026-04-23
**Scope**: All data handled by the AI Inbox Chief of Staff — raw email, derived
metadata, embeddings, LLM prompts + outputs, memories, audit records.
**Companion**: `threat-model.md` (H.1–H.4).

This policy assigns every category of data a **class**, and for each class
specifies where it can live, how long it can live there, what redaction applies
before it leaves the trust boundary, and how deletion is performed.

---

## 1. Classes

| Class | Definition | Examples |
|-------|------------|----------|
| **A — Sensitive User Content** | Raw contents of a user's email + anything from which those contents can be reconstructed verbatim. | `Email.body_text`, `Email.body_html`, `Email.subject`, `Email.snippet`, `Draft.draft_text`, `Brief.body_html/text`, attachment extracts. |
| **B — Derived User Data** | Features or representations that carry user-specific signal but not verbatim content. | Embeddings (`Email.embedding`, `Memory.embedding`), triage reasoning traces, feature dicts, brief item summaries, memory `content` fields, conversation messages. |
| **C — Operational Metadata** | Per-user identifiers, timestamps, statuses, correlation IDs. | Mailbox IDs, email IDs, history IDs, mutation statuses, triage outcomes, brief schedule times. |
| **D — Secrets** | Credentials or keys that grant access to user data or infrastructure. | Encrypted OAuth refresh + access tokens, `APP_SECRET_KEY`, webhook HMAC secrets, SES inbound secret, Slack webhook URL, PagerDuty routing key. |
| **E — Audit** | Append-only records of what the system or operator did, with sufficient detail to investigate incidents. | `AuditEvent` rows, `MutationLedger` rows. |

The rest of this doc is one table per class: *allowed storage*, *retention*,
*redaction*, *deletion workflow*, plus a separate section on the
verified-deletion path.

---

## 2. Class A — Sensitive User Content  (H.5–H.9)

### Allowed Storage
- **RDS Postgres (primary)**: `emails`, `drafts`, `briefs`, `brief_items`
  tables. Encrypted at rest via RDS-level encryption (AES-256, KMS-managed).
- **Worker memory (ephemeral)**: processed inside subagent tasks, never
  written to disk outside RDS.
- **LLM provider request bodies**: content sent to Anthropic / OpenAI /
  Gemini. Requires zero-retention mode on the provider key.
- **Prompt/embedding cache (Redis)**: 24h TTL on LLM outputs, 7d on
  embeddings. Cache is keyed by content hash; the plaintext key is *never*
  logged.

### Disallowed Storage
- Application logs (CloudWatch, stdout, Sentry, Datadog).
- Trace payloads (OTel collector).
- Alert sinks (Slack, PagerDuty): only metadata-class values permitted in
  `details`.
- S3 / GitHub / any third-party backup that is not RDS-snapshot.
- Local developer machines beyond the duration of an authenticated debug
  session.

### Retention
- **90 days** in `emails.body_text` / `body_html` / `snippet` / `subject`.
  Purged by `workers/data_retention.py` (`RETENTION_EMAIL_CONTENT_DAYS=90`).
- **90 days** for `attachment_extracts`.
- **90 days** for `drafts.draft_text` (piggybacks on email CASCADE).
- **180 days** for `brief_items.summary` + `key_points` (retention for audit of
  brief composition).
- LLM / embedding cache: 24h / 7d as above.

### Redaction Before Egress
- **Logs / traces**: structlog processor in `core/security/pii.py` scrubs
  addresses, phones, SSNs, card numbers, OAuth tokens. Bodies are never
  passed to loggers in the first place — reviewer responsibility enforced by
  PR review.
- **Alerts**: see §6 Class C; Class A fields must be replaced with counts or
  hashes.
- **Data export endpoint** (`api/routers/data_export.py`) returns Class A
  only to the authenticated *owning* user.

### Deletion Workflow
- User-initiated account deletion: `DELETE /data/delete-account` revokes
  tokens then cascades to all user rows (`api/routers/data_export.py`).
- TTL purge: nightly scheduler job
  (`workers/scheduler.py` → `workers/data_retention.py`).
- Single-email deletion: not currently exposed; out of scope for v1.

---

## 3. Class B — Derived User Data  (H.5–H.9)

### Allowed Storage
- RDS: `memories`, `memories.embedding`, `emails.embedding`, `emails.features`,
  `triage_decisions.reason_trace`, `brief_items.summary`,
  `assistant_messages.content`.
- pgvector IVFFlat indexes for `embedding` columns (RDS-local).
- LLM provider request bodies (same zero-retention requirement as Class A).

### Disallowed Storage
- Same as Class A. In particular, memory `content` fields commonly contain
  sender addresses and org names → must never appear in non-RDS sinks.

### Retention
- **365 days** for memories (`memory_decay.py` deactivates at 0.3 confidence
  after decay; not deleted until account delete).
- **180 days** for `triage_decisions.reason_trace`.
- **180 days** for `brief_items` (see Class A).
- Embeddings share the lifetime of their parent row.

### Redaction Before Egress
- Memory content surfaces in the operator UI — enforced by the standard
  auth dependency; internal read requires the memory's owning user session.
- Embeddings are **not** redactable after generation; treat leakage as
  equivalent to raw text leakage with degraded recall. Embedded vectors must
  not appear in logs, traces, alerts, or third-party sinks.

### Deletion Workflow
- Same as Class A.
- Memory-specific: `DELETE /memories/{id}` for per-row removal; soft-disable
  via `PATCH /memories/{id} {"is_active": false}`.
- Embedding column is dropped when its parent row is deleted (FK cascade).

---

## 4. Class C — Operational Metadata  (H.5–H.9)

### Allowed Storage
- RDS (freely).
- Application logs, traces, metrics, alert sinks (IDs, timestamps,
  correlation IDs, outcome enums, counts).
- OTel collector (traces), CloudWatch (metrics + logs), Slack / PagerDuty
  (alert `details`).

### Retention
- RDS: 365 days (bounded by `audit_events` retention).
- Logs: CloudWatch default 30d unless tagged for longer.
- Metrics: CloudWatch default 15 months for rollups.
- External alert services: per-vendor retention (Slack ~90d, PagerDuty ~13mo).

### Redaction
- No redaction required. But: **never augment Class C records with Class A/B
  fields**. Alert `details` is reviewed in PR for this.

### Deletion
- Account delete cascades RDS rows. Logs / metrics / vendor records are not
  retroactively purged — documented to users in the privacy notice.

---

## 5. Class D — Secrets  (H.5–H.11)

### Allowed Storage
- **AWS Secrets Manager** (prod): `APP_SECRET_KEY`, LLM provider keys,
  webhook HMAC secrets, SES/Slack/PagerDuty URLs + keys.
- **AWS KMS**: encryption key material for envelope encryption of OAuth
  tokens.
- RDS columns for OAuth tokens: stored only as *encrypted* ciphertext
  (`encrypted_refresh_token`, `encrypted_access_token`). Plaintext never
  persisted.

### Disallowed Storage
- Environment files checked into git (only `.env.example`, never real `.env`).
- Logs, traces, alerts — ever.
- Developer laptops in the clear (use `aws secretsmanager get-secret-value`
  at session start).

### Retention
- Tokens: lifetime of the mailbox connection. Revoked + deleted on disconnect
  (`core/gmail/auth.py::revoke_token()`).
- Other secrets: rotated per runbook (rotation cadence TBD — follow-up from
  threat model §1).

### Redaction
- PII scrubber includes token-prefix patterns to prevent accidental log
  leakage.
- Secrets never appear in error messages (verified by error-path tests).

### Deletion
- OAuth: revocation on disconnect + DB row clear.
- Other: KMS key deletion follows AWS deletion schedule (7–30d grace).

---

## 6. Class E — Audit  (H.9, H.13)

### Allowed Storage
- RDS `audit_events`, `mutation_ledger`. Immutable — DB trigger rejects
  UPDATE/DELETE on `audit_events` (see migration 001).
- Planned: S3 Object Lock export pipeline (X.10 TODO).

### Retention
- **365 days** in RDS.
- **7-year** target in S3 Object Lock (not yet implemented; H.18 TODO).

### Redaction
- Audit payloads are Class C by convention — identifiers + outcomes. Callers
  must not put Class A/B content into `AuditEvent.payload`.

### Deletion
- Audit is **not** deleted by user account-delete — only redacted (user_id
  set NULL via FK ON DELETE SET NULL). Compliance justification: investigate
  malicious-actor flows after an account is closed.

---

## 7. Approved Model Provider Routing  (H.11)

High-sensitivity flows (Class A → LLM) may route only to providers where:
1. Zero-retention mode is enabled on the API key.
2. The provider has a DPA covering the operator's jurisdiction.
3. Data-residency constraints, if any, are met at the API endpoint.

Current approved set:
- **Anthropic** (primary): zero-retention mode must be confirmed on the prod
  key; use `claude-opus-4-7` / `claude-sonnet-4-6` endpoints.
- **OpenAI** (fallback): zero-retention mode must be confirmed on the prod
  key; use chat/completions.

Not approved for high-sensitivity flows without explicit review:
- Google Gemini (I.8 TODO): pending DPA review.
- Any self-hosted model: pending.

The routing decision is enforced by `core/llm/client.py` provider order and
`core/llm/circuit_breaker.py`. A deny-list of providers can be added via
`settings.kill_switch_llm` or per-provider failure trip.

---

## 8. Verified Deletion Path  (H.10)

The user-initiated account delete path must demonstrably remove Class A/B/D
data. Verification steps (run in staging before Gate 7):

1. Seed a test account with ≥100 emails, ≥10 memories, ≥5 conversations, ≥5
   drafts, ≥5 briefs with items, ≥5 triage decisions, ≥5 mutation ledger
   entries.
2. Call `DELETE /data/delete-account`.
3. Confirm:
   - All rows with `user_id = <id>` are gone from `emails`, `memories`,
     `drafts`, `briefs`, `brief_items`, `triage_decisions`, `feedback_events`,
     `assistant_conversations`, `assistant_messages`, `mailboxes`.
   - `audit_events.user_id` and `mutation_ledger.user_id` are NULL (not
     deleted) — see §6 for rationale.
   - OAuth tokens are revoked at Google (check `/oauth2/v1/tokeninfo`).
   - LLM cache: Redis keys tied to the user's mailbox IDs are purged
     (worker TODO — currently rely on 24h TTL).
   - Logs: not purged (out of scope; see §4).

The verification script lives at `tests/integration/test_data_retention.py`
(integration-tier; the happy path is already covered).

---

## 9. Mapping to Phase-7 QA Gate

| Gate requirement | Satisfied by |
|---|---|
| H.5 Data classification (raw email, metadata, embeddings, prompts/outputs) | §1 + §§2–5 |
| H.6 Per-class: allowed storage locations | §§2–6 |
| H.7 Per-class: retention period | §§2–6 |
| H.8 Per-class: redaction requirements | §§2–6 |
| H.9 Per-class: deletion workflow | §§2–6 |
| H.10 Verified deletion path | §8 |
| H.11 Approved model-provider routing policy | §7 |

Outstanding follow-ups (each tracked in roadmap):
- Rotation runbook for `APP_SECRET_KEY` + KMS keys.
- S3 Object Lock audit export (X.10).
- Single-email deletion API + UI (post-launch).
- Allowlist of alert `details` keys to enforce §4 by schema rather than
  review.

---

## 10. Change Log

- **2026-04-23 (v1)**: Initial policy covering H.5–H.11. Classes defined,
  per-class controls codified, verified-deletion procedure documented.
