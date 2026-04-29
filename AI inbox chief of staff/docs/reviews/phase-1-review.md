# Phase 1 Review Packet — Gmail Ingestion + Canonical Email Model

**Status**: v1
**Companions**: `../PRODUCT_ROADMAP.md`, `../quality-gates.md`, `../risk-register.md`

---

## Header

| Field | Value |
|-------|-------|
| Phase | 1 — Gmail Ingestion + Canonical Email Model |
| Packet date | 2026-04-25 |
| Author | `<owner>` |
| Reviewers | `<names>` |
| Roadmap snapshot SHA | `<git sha>` |
| Related risks | R1 (OAuth consent), R5 (token theft) |

---

## 1. Phase Scope

| Roadmap ID | Feature | Status | Evidence |
|------------|---------|--------|----------|
| 1.1 | OAuth connect flow (per-mailbox) | PASS | `api/routers/auth.py` |
| 1.2 | CSRF state validation in OAuth callback | PASS | `core/security/csrf.py` Redis-backed, single-use, 10-min TTL |
| 1.3 | User identity from auth session | PASS | `core/security/auth.py` JWT session + `get_current_user` |
| 1.4 | Gmail watch registration | PASS | `GmailClient.register_watch()` |
| 1.5 | Gmail watch renewal cron (per-mailbox jitter) | PASS | `workers/scheduler.py` |
| 1.6 | History sync (incremental via historyId) | PASS | `IngestionAgent` history-delta path |
| 1.7 | Initial backfill on connect | PASS | `workers/backfill.py` (last 7 days, idempotent) |
| 1.8 | Gmail label creation on connect | PASS | `GmailClient.ensure_system_labels()` Cora/* labels |
| 1.9 | Idempotent ingestion | PASS | `(mailbox_id, gmail_message_id)` unique constraint |
| 1.10 | Feature extraction (sender reputation, domain, threading) | PASS | `_build_features()` + `core/gmail/reputation.py` |

---

## 2. Gate Criteria

| # | Criterion | Verification | Status |
|---|-----------|--------------|--------|
| 1.a | OAuth connect/callback/disconnect tests | `api/routers/auth.py` + integration tests blocked on consent screen | BLOCKED — R1 |
| 1.b | Idempotent ingestion | unique `(mailbox_id, gmail_message_id)` index + `IngestionAgent` duplicate test | PASS |
| 1.c | Mailbox isolation ≥ 2 mailboxes | `tests/integration/test_mailbox_isolation.py` | PASS |
| 1.d | Gmail watch registration + renewal | `workers/scheduler.py` sweep unit-tested; live test blocked on R1 | PARTIAL — R1 |
| 1.e | Rate-limited Gmail API | `core/gmail/rate_limiter.py` with tests | PASS |

---

## 3. Acceptance Evidence

- **Tests**: `pytest tests/unit/test_gmail* tests/integration/test_mailbox_isolation.py` — `<N>` passing on commit `<sha>`
- **Migrations**: 002 (pgvector + email columns) applied to integration DB
- **Integrations**: Gmail API client classes exercised against fixtures; live Google project pending R1
- **Code coverage delta**: ingestion path coverage ≥ 80%
- **PRs merged into main during this phase**: `<PR# range>`

---

## 4. Risk Delta

| Risk ID | Title | Pre-phase status | Post-phase status | Notes |
|---------|-------|------------------|-------------------|-------|
| R1 | Google Cloud OAuth consent screen not approved in time | n/a | OPEN | Auth code complete; consent screen submitted but unverified |
| R5 | OAuth refresh-token theft from DB | n/a | OPEN | Fernet-at-rest mitigates; rotation runbook still TBD |

No new risks introduced this phase beyond those already in the register.

---

## 5. Outstanding Items / Waivers

### Waiver: 1.a / 1.d — Live OAuth + watch-renewal tests blocked
- **Reason**: Both criteria require a Google Cloud project with an
  approved OAuth consent screen (R1). Code paths are written, unit-tested
  with mocks, and parameterized to flip from "limited audience" to
  "production" without code change.
- **Compensating control**: Limited-audience mode unblocks one operator
  testing on their own Gmail before full verification. CSRF + token
  encryption (1.2 + 0.4) reduce blast radius on misuse during the
  limited window. Once approved, both criteria can be re-validated in a
  single staging run before Gate 7 sign-off.
- **Revisit date**: First Friday after Google approval lands.
- **Owner**: `<owner>`
- **Tracked in**: `risk-register.md::R1`

---

## 6. Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineering | `<owner>` | `2026-04-25` | _______________ |
| Product / Owner | `<owner>` | `2026-04-25` | _______________ |

I confirm every PASS row in §2 has verifiable evidence in §3. The two
non-PASS rows (1.a BLOCKED, 1.d PARTIAL) carry a single waiver in §5
gated on R1, with a compensating control. Phase 1 is **conditionally
closed**: code-completeness sign-off granted; live-OAuth re-validation
required before Gate 7.

---

## Change Log

- `2026-04-25 (v1)`: Phase 1 closed conditionally pending R1 resolution.
  All code paths PASS; live integrations defer to consent-screen approval.
