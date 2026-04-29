# Threat Model

**Status**: Draft v1
**Last updated**: 2026-04-23
**Scope**: AI Inbox Chief of Staff — ingest path, triage/draft/brief agents, assistant control plane, operator surfaces.

This document enumerates the credible attack surfaces for production operation, the
assets they protect or threaten, the existing mitigations in code, and the gaps that
must close before launch.

Each section maps directly to a code reference so the claim can be verified. This
file and `data-classification.md` are the security prerequisites for Gate 7.

---

## 1. OAuth / Token Compromise  (H.1)

### Assets
- Per-mailbox Google OAuth refresh + access tokens (grants read + modify + draft-compose
  on a user's Gmail).
- Session JWTs for dashboard login.

### Threat Actors
- External: credential stealer, compromised vendor, rogue insider with DB read.
- Internal: operator with partial prod access.

### Attack Vectors
1. Exfiltration from the `mailboxes` table (encrypted-at-rest columns).
2. Leakage through logs, error reports, or traces.
3. Session token theft (XSS, shoulder-surf, transit interception).
4. OAuth consent screen impersonation or grant expansion.

### Mitigations (code-verified)
- **Envelope encryption** of refresh + access tokens with Fernet (dev) or KMS
  (prod): `core/security/encryption.py`. Plaintext never persisted.
- **No `gmail.send` scope** — the OAuth client requests only compose/modify/read.
  Verified by `tests/unit/test_security.py::test_no_send_scope`.
- **Revocation on disconnect**: `core/gmail/auth.py::revoke_token()` invoked from
  `api/routers/auth.py` on `/auth/gmail/disconnect`.
- **Proactive refresh** with jitter: `workers/scheduler.py` sweeps expiring tokens
  (avoids refresh-storm on mass expiry).
- **PII scrubbing** in structlog processor before any log sink:
  `core/security/pii.py` — regex-scrubs emails, phones, card numbers, OAuth tokens.
- **Session JWT**: short TTL, signed with `APP_SECRET_KEY`, HttpOnly cookie on
  the dashboard client (see `core/security/auth.py`).
- **CSRF** on OAuth callback: Redis-backed single-use state token with 10-min
  TTL (`core/security/csrf.py`).

### Residual Risks / Gaps
- No automated rotation of `APP_SECRET_KEY` yet — rotation procedure must be in
  runbook before Gate 7.
- No anomaly detection on OAuth refresh failures; a sudden burst of refresh
  failures from one IP would be missed by current alerts. **Follow-up**: add
  a rate-of-refresh-failure metric to the CloudWatch dashboard.
- KMS key policy + IAM roles for production not yet provisioned (tracked as
  X.3 "Cloud infrastructure provisioning" in the roadmap).

---

## 2. Prompt Injection via Email + Attachments  (H.2)

### Assets
- Model behavior integrity (triage outcomes, drafts, brief content).
- Downstream mutations (archives, label changes) that follow triage decisions.
- The writing-style policy (`skills/writing-style.md`) — attacker must not be
  able to override it.

### Threat Actors
- External: anyone who can send email to a user's inbox.
- Internal: malicious insider crafting emails on test mailboxes.

### Attack Vectors
1. Direct-injection payload in `Subject` / `body_text` / `snippet` fields
   ("ignore previous instructions…").
2. **Indirect** injection through attachments (PDF, DOCX, HTML) now that the
   system extracts attachment text (see X.11).
3. HTML-in-email tricks (hidden-text style, zero-width chars) to defeat naive
   sanitization.
4. Escalation attempts: "archive everything", "forward to …", "promote self
   to always_inbox".

### Mitigations (code-verified)
- **Hard-block detector** in `core/security/injection.py::sanitize_for_llm()`:
  17 adversarial patterns from `tests/safety/` must pass before enabling a new
  model.
- **Soft-strip** of role-confusion markers (`System:`, `Assistant:`, fenced
  role blocks) before content reaches the LLM.
- **System prompt preamble** in every LLM call reasserts the operator's
  instruction precedence (`get_system_prompt_preamble()`).
- **Attachment text truncation + bounded extractor**: `MAX_BYTES` = 20 MiB,
  `MAX_CHARS_PER_ATTACHMENT` = 50_000, binary types silently skipped; see
  `core/email/attachments.py`.
- **Safety-first fallback**: when injection is detected, TriageAgent returns
  `INBOX_KEEP` with `FALLBACK` method. No mutations apply
  (see `subagents/triage.py::_llm_classify`).
- **Draft grounding check**: drafts below `grounding_confidence=0.4` are
  persisted as `REJECTED` and never written to Gmail Drafts
  (`subagents/draft.py`).
- **No auto-send path**: OAuth scopes exclude `gmail.send`; tests assert this.
- **Mutation-guard + undo**: every mutation is ledgered with prior state and a
  7-day undo token. Even a successful prompt-injection-induced archive is
  reversible (`core/models/mutation_ledger.py`, `api/routers/undo.py`).

### Residual Risks / Gaps
- **Hidden-text / zero-width-char** defenses are regex-based and incomplete.
  Known gap: adversarial unicode homoglyphs. **Follow-up**: evaluate a
  unicode-normalization pass before sanitization.
- Attachment text is currently concatenated into the brief summarizer user
  message. If a PDF prompt-injects, the mitigation is the soft-strip — not
  tested against real attacker-crafted PDFs. **Follow-up**: add injection
  fixtures for PDFs to `tests/safety/` before enabling in auto mode.
- BriefAgent does not currently run the sanitizer on attachment extract text
  (only on `email.snippet`). Minor gap; fix is a one-liner.

---

## 3. Unauthorized Internal Access  (H.3)

### Assets
- Admin ability to read any user's mail metadata, policy memories, conversation
  history.
- Ability to mutate settings or delete data on another user's behalf.
- The prompt registry and experiment definitions.

### Threat Actors
- Internal operator with narrow vs. broad prod permissions.
- Compromised developer laptop or CI credential.

### Attack Vectors
1. API call from outside the authenticated flow (missing auth dependency).
2. Cross-tenant reads in queries that forget `WHERE user_id = …`.
3. Unrestricted `/docs` in production.
4. Internal admin tooling (e.g. Airflow, ad-hoc psql) bypassing audit.

### Mitigations (code-verified)
- **Every protected route** depends on `get_current_user` from
  `core/security/auth.py`. Confirmed by grepping for `@router.post|@router.get`
  across `api/routers/*`.
- **Mailbox isolation**: every query that touches mailbox-scoped data filters
  by `mailbox_id` AND validates `mailbox.user_id == user.id`. Integration
  coverage: `tests/integration/test_mailbox_isolation.py`.
- **Orchestrator checks ownership** before running subagents:
  `orchestrator/orchestrator.py` raises `PermissionError` on mismatch.
- **Docs disabled in production**: `api/main.py` sets `docs_url=None` when
  `settings.is_production`.
- **Immutable audit log**: `AuditEvent` rows are append-only; a DB trigger
  rejects UPDATE/DELETE (see migration 001).
- **Webhook auth**: Gmail Pub/Sub push endpoints require HMAC or Bearer token
  (`gmail_webhook_secret`); SES inbound requires `ses_inbound_secret` if set.

### Residual Risks / Gaps
- **No RBAC for internal admin tooling** — tracked as 6.12 TODO. Current
  assumption: internal ops uses read-only replicas + AWS IAM boundaries, not
  enforced in-app.
- **No break-glass admin audit**: direct DB access via AWS IAM would not
  produce app-level audit rows. Compensating control: CloudTrail + RDS
  performance insights, not yet wired as an evidence trail.
- **Supply-chain risk**: `pypdf` / `python-docx` are new required (optional)
  runtime deps; `pyproject.toml` should pin versions before production cut.

---

## 4. Data Exfiltration Paths  (H.4)

### Assets
- Raw email bodies + subjects (Class A data; see `data-classification.md`).
- Embeddings (Class B — leakage still leaks topic vectors).
- Memories (may contain sender addresses, org names).
- LLM prompts + responses to external providers.

### Threat Actors
- Compromised vendor (Anthropic, OpenAI, SES, PagerDuty, Slack sinks).
- Misconfigured log pipeline (CloudWatch → S3 → unintended share).
- Egress-point attacker with network access.

### Attack Vectors
1. Unbounded or unredacted content in logs / traces.
2. LLM provider request + response bodies cached or retained.
3. External alert sinks (Slack, PagerDuty) embedding sensitive fields.
4. Data export endpoint abused by attacker with stolen session.
5. Backup / snapshot theft.

### Mitigations (code-verified)
- **PII scrubbing** in structlog processor (`core/security/pii.py`): emails,
  phones, SSNs, cards, tokens all masked before every log sink.
- **Prompt/embedding cache** in `core/llm/cache.py` is keyed by content hash
  and stored in Redis (not shipped to vendors). TTLs enforced at 24h / 7d.
- **Per-mailbox token budget** cap: `core/llm/budget.py` prevents a single
  malicious actor from blowing out the LLM bill (cost-side exfil equivalent).
- **Alert sink payloads are summary-only**: `core/alerts/sinks.py` emits
  titles + key/value `details` (capped at 10 keys), never raw email content.
  Callers are expected to hand only metadata in `details`. This is a
  documentation + review gate, not an enforced schema.
- **Data export endpoint** (`api/routers/data_export.py`) requires
  authenticated user and exports only the caller's own data.
- **Retention TTLs**: `workers/data_retention.py` purges emails at 90d, triage
  decisions at 180d, audit log at 365d.
- **Circuit breaker + provider fallback** reduces sustained traffic to any one
  vendor (Anthropic → OpenAI on failure).

### Residual Risks / Gaps
- **Vendor data-retention guarantees not yet contractually verified**. Both
  Anthropic and OpenAI offer zero-retention modes; must be enabled in the
  production API keys. **Follow-up**: verify before Gate 7.
- **Alert details are free-form dicts** — nothing prevents a future caller
  from putting `email.body_text` in a Slack alert. Compensating control: PR
  review; firmer control would be an allowlist of detail keys.
- **Backup / snapshot encryption** is inherited from RDS defaults. Key
  management + snapshot copy policies not yet codified; tracked as part of
  H.19 (backup/restore drill).
- **Embedding leakage** is an underappreciated class: embeddings can be
  inverted to approximate text. Treated as Class B in the data classification
  doc but no redaction applied to embeddings themselves.

---

## 5. Mapping to Phase-7 QA Gate

| Gate requirement | Satisfied by |
|---|---|
| H.1 Threat model: OAuth/token compromise | §1 |
| H.2 Threat model: prompt injection (email + attachments) | §2 |
| H.3 Threat model: unauthorized internal access | §3 |
| H.4 Threat model: data exfiltration paths | §4 |

Outstanding follow-ups captured above. None block writing the data
classification policy (H.5–H.11) — that doc enumerates per-class controls
referenced here.

---

## 6. Change Log

- **2026-04-23 (v1)**: Initial enumeration covering H.1–H.4. Mitigations reflect
  code as of commit range ending with the A/B testing framework +
  attachment extraction + SES inbound + alert routing merges.
