# AI Inbox Chief of Staff — Product Roadmap

> **Purpose**: Living document of planned-but-not-yet-implemented features.
> Claude Code should reference this before starting work and update it as features ship.
>
> **Last updated**: 2026-04-28 (Tier B sweep: 79 new tests across Gates 2–6 — eval-run, drafting/grounding/style, brief delivery + mailbox isolation, instruction parsing, memory scope, resilience (retry/DLQ/replay/partial outage). Gate 7 regression green at 356/356)

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| DONE | Implemented and tested |
| PARTIAL | Code exists but incomplete or stubbed |
| TODO | Not yet started |

---

## Phase 0 — Foundations

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 0.1 | Project scaffolding (pyproject, docker-compose, alembic) | DONE | |
| 0.2 | ORM models (all 11 tables) | DONE | |
| 0.3 | Typed stage contracts | DONE | `core/schemas/contracts.py` |
| 0.4 | Security: encryption (Fernet/KMS) | DONE | `core/security/encryption.py` |
| 0.5 | Security: prompt injection detection | DONE | 17 adversarial tests passing |
| 0.6 | Gmail OAuth (no send scope) | DONE | Auth + client classes |
| 0.7 | LLM client with provider fallback | DONE | Anthropic primary, OpenAI fallback |
| 0.8 | All 9 subagents + orchestrator | DONE | |
| 0.9 | API layer (health, auth, webhooks, mailboxes, assistant, undo) | DONE | |
| 0.10 | Workers (ingest, scheduler) | DONE | |
| 0.11 | Terraform infra (VPC, RDS, SQS, ECS, monitoring) | DONE | Not yet provisioned |
| 0.12 | Unit tests (97 passing) | DONE | |
| 0.13 | Integration tests (SQLite compat + Postgres) | DONE | SQLite: patched types; Postgres: 19 pgvector/JSONB/enum/cascade/trigger tests |
| 0.14 | CI/CD pipeline (GitHub Actions) | DONE | Backend lint+unit+integration, frontend build, security scan, ECR+ECS deploy |
| 0.15 | Environments (dev/staging/prod) config | PARTIAL | `.env.example` exists; no staging/prod deploy |

---

## Phase 1 — Gmail Ingestion + Canonical Email Model

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1.1 | OAuth connect flow (per-mailbox) | DONE | `api/routers/auth.py` |
| 1.2 | CSRF state validation in OAuth callback | DONE | `core/security/csrf.py` — Redis-backed state with 10-min TTL, single-use |
| 1.3 | User identity from auth session | DONE | `core/security/auth.py` — JWT session, `get_current_user` dependency on all protected endpoints |
| 1.4 | Gmail watch registration | DONE | `GmailClient.register_watch()` |
| 1.5 | Gmail watch renewal cron (per-mailbox with jitter) | DONE | `workers/scheduler.py` |
| 1.6 | History sync (incremental via historyId) | DONE | `IngestionAgent` fetches history delta |
| 1.7 | Initial backfill on connect | DONE | `workers/backfill.py` — fetches last 7 days, idempotent via dedup constraint |
| 1.8 | Gmail label creation on connect | DONE | `GmailClient.ensure_system_labels()` creates Cora/* labels; IDs stored on Mailbox |
| 1.9 | Idempotent ingestion | DONE | `(mailbox_id, gmail_message_id)` unique constraint |
| 1.10 | Feature extraction (sender reputation, domain, threading) | DONE | `_build_features()` + `core/gmail/reputation.py` sender scoring |

---

## Phase 2 — Triage Engine v1

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 2.1 | Deterministic rule engine | DONE | AlwaysInbox, Newsletter, DirectReply rules |
| 2.2 | LLM classifier fallback | DONE | `TriageAgent._llm_classify()` |
| 2.3 | Confidence scoring + fallback handling | DONE | Thresholds in config |
| 2.4 | Retrieval of similar past emails for triage context | DONE | pgvector cosine similarity search in `TriageAgent._retrieve_similar_emails()` |
| 2.5 | Memory-informed triage (load mailbox preferences) | DONE | TriageAgent loads mailbox + user-global memories, passes to rules + LLM |
| 2.6 | Triage correction feedback loop | DONE | `api/routers/feedback.py` — correction → memory update → behavior change |
| 2.7 | Protected sender/thread/category rules | DONE | Protected senders manageable per-mailbox via the mailbox settings page; creates `always_inbox` memories consumed by `AlwaysInboxRule` |
| 2.8 | Per-mailbox rate limiting (Gmail API + LLM tokens) | DONE | `core/gmail/rate_limiter.py` (Gmail API) + `core/llm/budget.py` (LLM tokens) |

---

## Phase 3 — Drafting in User Voice

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 3.1 | Draft generation with writing-style policy | DONE | `DraftAgent` loads `skills/writing-style.md` |
| 3.2 | Gmail Draft creation (compose only) | DONE | `GmailClient.create_draft()` |
| 3.3 | Grounding score + hallucination flag | DONE | LLM returns `grounding_confidence` |
| 3.4 | Voice profile from sent-mail embeddings | DONE | `core/style/profile.py` extracts style from sent mail; injected into DraftAgent |
| 3.5 | Style extraction pipeline | DONE | `workers/style_extraction.py` — weekly refresh per mailbox |
| 3.6 | Draft quality constraints (reference grounding to original thread) | DONE | Auto-reject drafts with grounding_score < 0.4; status=REJECTED |
| 3.7 | Draft edit tracking (user edits -> style refinement) | DONE | `workers/draft_tracker.py` — diff tracking with edit_distance scoring |
| 3.8 | Multi-turn thread context in drafts | DONE | Loads up to 5 prior thread messages as context in DraftAgent |

---

## Phase 4 — Brief System

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 4.1 | Brief scheduler (morning/afternoon windows) | DONE | `workers/scheduler.py` |
| 4.2 | Brief composition (HTML + text) | DONE | `BriefAgent` |
| 4.3 | Category grouping (newsletters, updates, etc.) | DONE | LLM assigns category per item |
| 4.4 | Brief delivery via email | DONE | `core/email/ses.py` — Amazon SES delivery gated on `SES_ENABLED` |
| 4.5 | Minimal web view for brief history | DONE | `/briefs` list + `/briefs/[id]` detail; grouped by category with Gmail open links |
| 4.6 | Quick-open links back to Gmail | DONE | `gmail_open_url` in BriefItem |
| 4.7 | Per-mailbox brief preferences (enable/disable, time windows) | DONE | Mailbox page exposes brief enable/disable plus morning + afternoon hour pickers |
| 4.8 | Importance scoring and ordering within brief | DONE | Items sorted by `importance_score` descending before composing brief |

---

## Phase 5 — Assistant + Memory

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 5.1 | Natural language instruction endpoint | DONE | `api/routers/assistant.py` |
| 5.2 | Policy compilation (instruction -> rules) | DONE | `PolicyAgent` |
| 5.3 | Memory extraction from feedback | DONE | `MemoryAgent` |
| 5.4 | Memory scoping (mailbox vs user-global) | DONE | `scope` enum + `applies_to_all_mailboxes` |
| 5.5 | pgvector embedding columns for memory retrieval | DONE | Migration 002; `Vector(1536)` on memories + emails; IVFFlat indexes |
| 5.6 | Semantic memory search (vector similarity) | DONE | `MemoryQueryAgent._semantic_search()` with cosine_distance fallback |
| 5.7 | Clarifying follow-ups for ambiguous instructions | DONE | `PolicyAgent` two-step: ambiguity check → extract or ask clarification |
| 5.8 | Web chat assistant interface | DONE | Superseded by X.12 — `/assistant` is a full threaded chat (multi-conversation, scope picker, optimistic UI). U.7 adds proactive suggestions on top |
| 5.9 | Email-based command endpoint | DONE | `POST /webhooks/ses-inbound` parses SNS-wrapped SES payload, matches sender to user, creates `AssistantConversation` + runs PolicyAgent; bearer auth via `ses_inbound_secret` |
| 5.10 | Memory confidence decay and expiry | DONE | `workers/memory_decay.py` — 5%/week decay, 0.3 deactivation threshold |
| 5.11 | Behavioral signal memory (undo/reclassify/edit -> memory update) | DONE | `workers/behavioral_signals.py` — undo/correction/edit signal extraction |

---

## Phase 6 — Reliability, Security, and Cost Hardening

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 6.1 | Token encryption (Fernet dev / KMS prod) | DONE | |
| 6.2 | Prompt injection defense | DONE | Hard-block + soft-strip + preamble |
| 6.3 | Mutation ledger + undo | DONE | 7-day undo window |
| 6.4 | Kill switches (LLM + mutations) | DONE | Config flags checked in BaseAgent |
| 6.5 | Immutable audit log (DB trigger) | DONE | Migration creates trigger |
| 6.6 | DLQ + retry strategy | DONE | SQS redrive with 3 retries per queue |
| 6.7 | PII scrubbing in logs/traces | DONE | `core/security/pii.py` — regex scrub for emails, phones, SSNs, cards, tokens; structlog processor |
| 6.8 | Token budget enforcement (per-mailbox daily cap) | DONE | `core/llm/budget.py` — Redis-backed daily/monthly caps with auto-degradation at 80% |
| 6.9 | Cheaper model routing for low-stakes tasks | DONE | `ModelTier.HIGH/LOW` in `core/llm/client.py`; Haiku for briefs |
| 6.10 | Prompt/embedding caching | DONE | `core/llm/cache.py` — Redis-backed, 24h LLM / 7d embedding TTL |
| 6.11 | Token rotation (OAuth refresh token renewal) | DONE | `core/gmail/auth.py` — proactive refresh in scheduler sweep |
| 6.12 | RBAC for internal admin tooling | DONE | `UserRole` enum (migration 006) + `require_admin` dependency in `core/security/auth.py`; `api/routers/admin.py` exposes `/admin/users`, `/admin/activity-stats`, `/admin/users/{id}/role` with admin-only access; self-demote guard prevents lockout |
| 6.13 | Data retention/deletion policy | DONE | `workers/data_retention.py` — 90d email, 180d triage, 365d audit TTLs |
| 6.14 | User data export workflow (GDPR) | DONE | `api/routers/data_export.py` — export + cascading delete with token revocation |
| 6.15 | DLQ replay workflow | DONE | `workers/dlq_replay.py` — selective replay with dry-run, mailbox filter |
| 6.16 | Circuit breaker per provider | DONE | `core/llm/circuit_breaker.py` — sliding window, 5-failure trip, 120s cooldown |
| 6.17 | Webhook HMAC validation (Google Pub/Sub) | DONE | Bearer token + HMAC fallback verification in `webhooks.py` |
| 6.18 | Incident alert routing (PagerDuty/Slack) | DONE | `core/alerts/` pluggable sinks (Slack webhook, PagerDuty Events v2); wired into circuit breaker trip + DLQ replay errors; fail-closed (alerting can't itself crash the pipeline) |

---

## Phase 7 — Acceptance + Launch

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 7.1 | Shadow mode (observe + log, no mutations) | DONE | `SHADOW_MODE=true` skips mutations + Gmail drafts; logs all decisions |
| 7.2 | Controlled activation (progressive rollout) | DONE | Per-mailbox `activation_mode` (shadow/observe/auto); orchestrator respects it |
| 7.3 | Launch SLOs defined and monitored | DONE | 13 targets codified in `core/slo/targets.py`; measurements in `core/slo/metrics.py` over existing rows; `GET /slo/status` aggregates with pass/warn/fail/not_measured; `/slo` dashboard groups by category + surfaces critical-gate launch-readiness banner |
| 7.4 | User controls to pause/resume features | DONE | `/mailbox/[id]` exposes `brief_enabled` / `draft_enabled` / `auto_archive_enabled` toggles + `activation_mode` selector (shadow/observe/auto) |
| 7.5 | Undo/recover UI for routing decisions | DONE | Activity > Undo tab lists recent mutations with one-click undo |
| 7.6 | Gold eval dataset from real inbox samples | TODO | |
| 7.7 | Nightly evaluation pipeline | DONE | `workers/nightly_eval.py` — runs 4 eval types per mailbox nightly |
| 7.8 | Prompt version registry | DONE | `core/prompts/registry.py` — versioned templates with A/B support |
| 7.9 | A/B testing framework for prompts | DONE | `Experiment`/`ExperimentVariant` models; migration 004; deterministic hash assignment in `core/prompts/experiments.py`; two-proportion z-test rollup; full CRUD API; `/experiments` UI; TriageAgent resolves variant at classification time |

---

## Cross-Cutting Features (Not Phase-Specific)

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| X.1 | Frontend dashboard (React/Next.js) | DONE | Next.js 16 + @base-ui — 15 routes; shared primitives (`StatCard`/`ListRow`/`EmptyState`/`SectionHeader`/`PageSkeleton`); semantic color tokens (`--success`/`--warning`/`--info`); onboarding welcome card; URL-synced filters on memories/briefs/activity; breadcrumbs in dashboard header |
| X.2 | Google Cloud project setup (OAuth consent screen) | TODO | Required before any real Gmail connection |
| X.3 | Cloud infrastructure provisioning (terraform apply) | TODO | All Terraform written; not applied |
| X.4 | GitHub Actions CI/CD pipeline | DONE | Backend lint+test+integration, frontend build, security scan, ECR deploy, ECS staging |
| X.5 | Integration tests on real Postgres | DONE | 19 tests: pgvector, JSONB, enums, cascades, audit trigger, IVFFlat indexes |
| X.6 | Load testing (k6 or locust) | TODO | |
| X.7 | Staging environment | TODO | |
| X.8 | Production environment | TODO | |
| X.9 | Observability: distributed tracing (Jaeger/X-Ray) | PARTIAL | OTel collector config exists; no trace backend |
| X.10 | S3 audit export pipeline | TODO | Audit events in DB only |
| X.11 | Attachment text extraction | DONE | `core/email/attachments.py` extracts PDF (pypdf) + DOCX (python-docx) + plain + html; ingestion downloads via `GmailClient.get_attachment()`, stores on `Email.attachment_extracts` JSONB; BriefAgent surfaces attachment context in summaries |
| X.12 | Multi-turn conversation state for assistant | DONE | `AssistantConversation`/`AssistantMessage` models; migration 003; `/assistant` page is now a full threaded chat with conversation list + delete |

---

## Integrations Inventory

External services required for full production operation. Each must be wired in code/config with secrets in Secrets Manager and egress allowlists.

### Required Integrations

| # | Integration | Status | Phase | Notes |
|---|-------------|--------|-------|-------|
| I.1 | Google Cloud project (OAuth consent screen, quotas) | TODO | 0 | Required before any real Gmail connection |
| I.2 | Gmail API (messages, labels, history, drafts, watch) | DONE | 1 | Client class complete; needs real project |
| I.3 | Gmail OAuth 2.0 (client ID/secret, refresh token storage) | DONE | 1 | Auth flow built; no real credentials yet |
| I.4 | Gmail push notifications (webhook or Pub/Sub) | DONE | 1 | Webhook endpoint exists; Pub/Sub alt not built |
| I.5 | Google OAuth token revocation on disconnect | DONE | 1 | `core/gmail/auth.py:revoke_token()` called on disconnect |
| I.6 | Anthropic API (messages) | DONE | 2 | Primary LLM provider |
| I.7 | OpenAI API (chat/completions) | DONE | 2 | Fallback LLM provider |
| I.8 | Google Gemini API (routing/cost tier) | TODO | 2 | Optional cheaper model for low-stakes tasks |
| I.9 | Amazon SES (brief delivery + transactional email) | DONE | 4 | `core/email/ses.py` — SESClient with HTML/text delivery; needs domain verification |
| I.10 | Auth provider (Auth0/Clerk/Cognito or custom JWT) | TODO | 5 | Separate from Gmail OAuth — "login to dashboard" identity |
| I.11 | SES Inbound Parse (assistant email channel) | TODO | 5 | User forwards email to dedicated address → assistant command |
| I.12 | Frontend hosting (Vercel/S3+CloudFront) | TODO | 5 | CORS locked to known origins |

### Recommended Integrations

| # | Integration | Status | Phase | Notes |
|---|-------------|--------|-------|-------|
| I.13 | PagerDuty/Opsgenie (on-call routing) | TODO | 6 | CloudWatch → SNS → PagerDuty |
| I.14 | Sentry (error aggregation with PII scrubbing) | TODO | 6 | API + worker error tracking |
| I.15 | AWS WAF on ALB (rate limiting, bot protection) | TODO | 6 | |
| I.16 | ClamAV sidecar or malware scan API | TODO | 6 | Before deep-parsing email attachments |
| I.17 | MIME parsing + document text extraction (pdf/doc) | TODO | 4+ | For attachment summaries in briefs |
| I.18 | SIEM forward (CloudTrail + app audit logs) | TODO | 7 | Long-term retention compliance |

### Optional / Future Integrations

| # | Integration | Status | Phase | Notes |
|---|-------------|--------|-------|-------|
| I.19 | Stripe/Paddle (subscriptions) | TODO | Post-launch | Required for SaaS; store only Stripe customer ID |
| I.20 | Google Workspace domain-wide delegation | TODO | Post-launch | Only if enterprise admin-controlled accounts needed |
| I.21 | Datadog/Honeycomb (APM) | TODO | Post-launch | Alternative to CloudWatch+X-Ray stack |

### Integration Phase Mapping

- **Phase 0**: AWS account, VPC, ECR, ECS skeleton, Secrets Manager, KMS, GitHub Actions OIDC
- **Phase 1**: Gmail OAuth, Gmail API, webhook/Pub/Sub, RDS, Redis, SQS
- **Phases 2–4**: LLM providers, SES (brief mail), EventBridge schedules
- **Phase 5**: Assistant inbound email (SES inbound), auth provider for dashboard login
- **Phases 6–7**: PagerDuty, Sentry, WAF, backup/restore drills, full audit pipeline

---

## User Interaction Model

### Primary Mode: Background Automation

The system runs continuously without requiring a dashboard to be open:
- Ingests new mail per mailbox
- Triages per mailbox rules + LLM
- Creates drafts for actionable emails
- Sends scheduled mailbox-specific briefs

| # | Control Surface | Status | Notes |
|---|----------------|--------|-------|
| U.1 | Web dashboard: connect/disconnect mailboxes | DONE | Dashboard page + mailbox detail page |
| U.2 | Web dashboard: mailbox-specific preferences | DONE | `/mailbox/[id]` with activation mode + feature toggles |
| U.3 | Web dashboard: review briefs, drafts, decisions | DONE | `/briefs` + Activity > Corrections list with pickable decisions |
| U.10 | Web dashboard: view/edit/delete learned memories | DONE | `/memories` page with filters, inline edit, active toggle, delete |
| U.4 | Web dashboard: issue assistant instructions | DONE | `/assistant` page |
| U.5 | Web dashboard: trigger undo on mutations | DONE | Activity > Undo tab: list of recent mutations with one-click undo |
| U.6 | Email interaction: forward/reply to assistant address | TODO | Needs SES inbound parse (I.11) |
| U.7 | Chat panel: conversational control plane | DONE | `/assistant` page surfaces deterministic rule suggestions from recent corrections + discarded drafts via `GET /assistant/suggestions`; one-click "Use this" pre-fills the chat. Activity > Corrections has a "Discuss in chat" deep link that pre-fills decision context |
| U.8 | User-facing transparency panel ("what happened" feed) | DONE | `/transparency` route — unified per-mailbox chronological timeline fusing triage_decisions + mutation_ledger + drafts + audit_events; cursor pagination; per-kind filter chips. Backed by `GET /activity/timeline` |
| U.9 | Operator telemetry dashboard (internal) | PARTIAL | CloudWatch dashboard exists; no custom UI |

---

## Compound Engineering Governance Artifacts

The plan mandates specific artifacts at phase gates. These are process deliverables, not code.

### Pre-Phase 0 Entry Gate

| # | Artifact | Status | Notes |
|---|----------|--------|-------|
| G.1 | Repo system audit (`compound-engineering/00-repo-system-audit.md`) | PARTIAL | `docs/threat-model.md` + `docs/data-classification.md` + `docs/quality-gates.md` together provide the audit surface; standalone artifact deferred |
| G.2 | Development process audit (`compound-engineering/01-development-process-audit.md`) | PARTIAL | `docs/pr-review-checklist.md` + `docs/incident-operations.md` cover process hot-paths; deeper audit deferred |
| G.3 | Feature plan packet (from `04-templates/plan-template.md`) | PARTIAL | Plan file exists; formal packet not instantiated |
| G.4 | Initial risk register (top 10 delivery risks) | DONE | `docs/risk-register.md` — 10 risks covering delivery/security/reliability/product, all scored |
| G.5 | Validate `skills/writing-style.md` readable | DONE | DraftAgent + BriefAgent block if missing |

### Phase 0–2 Gate Artifacts

| # | Artifact | Status | Notes |
|---|----------|--------|-------|
| G.6 | Active risk register maintained (2x/week updates) | DONE | Cadence documented in `docs/risk-register.md` + `docs/incident-operations.md` §5 |
| G.7 | Quality gate checklist per phase (`05-checklists/quality-gate-checklist.md`) | DONE | `docs/quality-gates.md` — pass/fail + waiver template for every gate |
| G.8 | PR review checklist for all merge candidates | DONE | `docs/pr-review-checklist.md` — tiered (light/standard/deep), paste-in skeleton |

### Phase 3–5 Gate Artifacts

| # | Artifact | Status | Notes |
|---|----------|--------|-------|
| G.9 | Memory-spec conformance notes (`10-compound-memory-spec.md`) | TODO | |
| G.10 | Per-phase review packets (`04-templates/review-template.md`) | TODO | |
| G.11 | User feedback-to-rule conversion metrics (weekly) | TODO | |

### Phase 6–7 Gate Artifacts

| # | Artifact | Status | Notes |
|---|----------|--------|-------|
| G.12 | Governance/triage readiness (`09-governance-and-triage.md`) | DONE | `docs/incident-operations.md` covers severity matrix + PIR + on-call routing |
| G.13 | Release readiness checklist (`04-templates/release-readiness-template.md`) | DONE | `docs/release-readiness.md` — 8-section verifier with sign-off block |
| G.14 | Handoff checklist (`05-checklists/handoff-checklist.md`) | PARTIAL | Covered implicitly by `release-readiness.md` §7; standalone handoff deferred until a second operator is onboarding |
| G.15 | Retrospective (`04-templates/compound-retrospective-template.md`) | TODO | Expected post-launch |
| G.16 | Launch decision memo | DONE | `docs/launch-decision-memo-template.md` — instantiate per launch |

---

## Production Hardening Addendum

Detailed requirements from the plan that go beyond the Phase 6 feature table.

### 1) Threat Model

| # | Item | Status | Notes |
|---|------|--------|-------|
| H.1 | Threat model document covering OAuth/token compromise | DONE | `docs/threat-model.md` §1 |
| H.2 | Threat model: prompt injection via email + attachments | DONE | `docs/threat-model.md` §2 |
| H.3 | Threat model: unauthorized internal access | DONE | `docs/threat-model.md` §3 |
| H.4 | Threat model: data exfiltration paths (logs, queues, vendor APIs) | DONE | `docs/threat-model.md` §4 |

### 2) High-Sensitivity Data Controls

| # | Item | Status | Notes |
|---|------|--------|-------|
| H.5 | Data classification (raw email, metadata, embeddings, prompts/outputs) | DONE | `docs/data-classification.md` §1 + §§2–5 |
| H.6 | Per-class: allowed storage locations | DONE | `docs/data-classification.md` §§2–6 |
| H.7 | Per-class: retention period | DONE | `docs/data-classification.md` §§2–6 |
| H.8 | Per-class: redaction requirements | DONE | `docs/data-classification.md` §§2–6 |
| H.9 | Per-class: deletion workflow | DONE | `docs/data-classification.md` §§2–6 |
| H.10 | Verified deletion path for user data requests | DONE | `docs/data-classification.md` §8 |
| H.11 | Approved model provider routing policy (high-sensitivity flows) | DONE | `docs/data-classification.md` §7 |

### 3) Autonomous Action Safety

| # | Item | Status | Notes |
|---|------|--------|-------|
| H.12 | Confidence-based action policy (high/medium/low thresholds) | DONE | MutationGuardAgent |
| H.13 | Complete mutation ledger (prior/new state, reason, undo token) | DONE | |
| H.14 | Undo support within policy window | DONE | 7-day window |
| H.15 | "Always inbox" / "never archive" highest-precedence rules | DONE | AlwaysInboxRule + mailbox-page UI to add/remove protected senders and domains |

### 4) Reliability, SLO, and Recovery

| # | Item | Status | Notes |
|---|------|--------|-------|
| H.16 | SLO definitions instrumented in dashboards | DONE | Math codified in `core/slo/`; exposed via `/slo/status` for in-app dashboard; CloudWatch alarm wiring (external) remains as infra work |
| H.17 | RTO target for brief/draft pipeline: <= 60 min | TODO | Not tested |
| H.18 | RPO target for decision/memory/audit: <= 5 min | TODO | RDS backup interval not validated |
| H.19 | Backup/restore drill executed and evidence recorded | TODO | |
| H.20 | Dead-letter replay tooling with idempotent reprocessing | TODO | |

### 5) Incident Operations

| # | Item | Status | Notes |
|---|------|--------|-------|
| H.21 | Severity matrix (sev0–sev3) with response SLAs | DONE | `docs/incident-operations.md` §1 — MTTA + mitigation-start + comms cadence per sev |
| H.22 | Runbook: Gmail webhook/watch failure | DONE | `docs/runbooks/gmail-watch-failure.md` |
| H.23 | Runbook: model provider outage/rate limit | DONE | `docs/runbooks/model-provider-outage.md` |
| H.24 | Runbook: false-archive spike | DONE | `docs/runbooks/false-archive-spike.md` |
| H.25 | Runbook: anomalous draft behavior | DONE | `docs/runbooks/anomalous-draft.md` |
| H.26 | On-call routing verified (PagerDuty/Opsgenie) | TODO | |
| H.27 | Post-incident review process linked to risk register | DONE | `docs/incident-operations.md` §4 — PIR template + T+1/T+3/T+30 cadence linking back to risk register |

---

## QA Gates (Per-Milestone Pass/Fail Criteria)

Each gate must pass before its phase is marked complete. Failures pause progress.

### Gate 0 — Day-0/Phase-0 Foundation

| Criterion | Status |
|-----------|--------|
| CI pipeline green on baseline test suite | PARTIAL | Unit tests pass; CI pipeline not built |
| Config/secret loading tests for dev + staging | TODO |
| Health endpoints + service startup smoke tests | DONE |

### Gate 1 — Gmail Connect + Ingestion (Phase 1)

| Criterion | Status |
|-----------|--------|
| OAuth connect/disconnect tests | TODO | Needs real Google project |
| Gmail watch registration + renewal tests | TODO |
| Idempotent ingestion tests (duplicate handling) | DONE | Unit test covers |
| Mailbox isolation for >= 2 mailboxes | PARTIAL | Integration tests written, blocked by SQLite |

### Gate 2 — Triage Engine (Phase 2)

| Criterion | Status |
|-----------|--------|
| Rule-engine unit tests + precedence | DONE | 12 tests passing |
| LLM fallback path (provider unavailable → deterministic) | DONE | Code path exists |
| Confidence threshold policy tests | DONE |
| False-brief/false-archive eval sample run | DONE | `tests/integration/test_gate2_eval_run.py` (8 tests) — fixture-loader → labelled gold samples → `core/slo/metrics.py` rate computation, threshold-crossing assertions. Real-mailbox ≥100-sample labelling still blocked on R3/OAuth (waiver in `docs/reviews/phase-2-review.md` §5) |

### Gate 3 — Drafting (Phase 3)

| Criterion | Status |
|-----------|--------|
| Draft generation integration with grounding checks | DONE | `tests/integration/test_gate3_draft_grounding.py` (5 tests) — high/low grounding, hallucination flag, multi-turn 5-message context cap |
| No-send guardrail tests (gmail.send absent) | DONE | 4 unit tests |
| Writing-style policy injection tests | DONE | `tests/integration/test_writing_style_injection.py` extended to 9 tests — assembled-prompt verbatim policy, sent-mail voice profile injection, edit-feedback creates STYLE memory |
| Draft quality eval sample passes minimum bar | DONE | `tests/integration/test_gate3_draft_quality_eval.py` (3 tests) — fixture-driven aggregate conformance ≥ 0.30 signal floor; live-LLM swap deferred to OAuth |

### Gate 4 — Brief Pipeline (Phase 4)

| Criterion | Status |
|-----------|--------|
| Schedule trigger tests (morning/afternoon) | DONE | `tests/unit/test_brief_scheduler.py` extended (16 tests) — window selection, jitter bounds + determinism, brief_enabled flag honored, importance ordering preserved |
| Brief composition tests (category + summary) | DONE | `tests/unit/test_brief_composition.py` extended (15 tests) — category grouping, empty-mailbox path, importance sort, gmail_open_url, HTML+text variants |
| Delivery tests (email and/or web view) | DONE | `tests/integration/test_gate4_brief_delivery.py` (6 tests) — SES_ENABLED on/off paths, SES error → DELIVERY_FAILED + alert sink, /briefs cross-user 404 |
| Mailbox-specific brief isolation (no unified digest) | DONE | `tests/integration/test_gate4_brief_mailbox_isolation.py` (5 tests) — per-mailbox briefs, no cross-mailbox item bleed, per-mailbox preferences honored |

### Gate 5 — Assistant + Memory (Phase 5)

| Criterion | Status |
|-----------|--------|
| Instruction parsing correctness | DONE | `tests/integration/test_gate5_instruction_parsing.py` (4 tests) — clear-instruction extraction, ambiguity → clarifying question, multi-turn clarification, mailbox vs user-global scope routing |
| Memory write/read with scope correctness | DONE | `tests/integration/test_gate5_memory_scope.py` (4 tests) — mailbox-scoped retrieval isolation, user-global cross-mailbox retrieval, scope respected in MemoryQueryAgent (text-search fallback path; pgvector path identical scope filter) |
| Feedback loop: correction → memory → behavior change | DONE | `tests/integration/test_feedback_loop_e2e.py` extended — two-cycle test: triage → correction → memory write → next similar email triaged differently |
| Prompt-injection adversarial tests on assistant | DONE | 17 tests |

### Gate 6 — Hardening (Phase 6)

| Criterion | Status |
|-----------|--------|
| Token encryption + RBAC + audit completeness | PARTIAL | Encryption done; RBAC and audit completeness TODO |
| Resilience tests (retry, DLQ, replay, partial outage) | DONE | `tests/resilience/` — 20 tests across DLQ replay (5), retry/circuit-breaker (10), partial-outage isolation (5). Circuit-breaker timing tested via `time.monotonic` patching |
| Backup/restore drill success | TODO | Tier C — needs staging up |
| Alerting test (simulated sev1 → route + ack) | TODO | Tier C — needs staging up + PagerDuty/Slack sinks live |

### Gate 7 — Launch (Phase 7)

| Criterion | Status |
|-----------|--------|
| Full regression suite green | TODO |
| Numeric launch targets met (or documented waiver) | TODO |
| Runbook walkthrough by non-author operator | TODO |
| Handoff + release readiness artifacts complete | TODO |

---

## Numeric Launch Targets (Detailed)

From the plan's "Initial Numeric Launch Targets" — thresholds for first production launch, to be tightened after 2–4 weeks of live telemetry.

### Quality and Safety

| Metric | Target | Status |
|--------|--------|--------|
| False-archive rate (7-day rolling) | <= 0.5% | DONE — `false_archive_rate` measurement over `mutation_ledger` |
| False-brief rate (7-day rolling) | <= 1.0% | DONE — `false_brief_rate` over `triage_decisions` |
| Draft factual/grounding failure rate | <= 1.5% | DONE — `draft_grounding_failure_rate` over `drafts` |
| Prompt-injection safety eval pass rate | >= 99.0% | DONE — 100% on current suite; surfaced statically in `/slo` |
| Style-conformance pass rate (`writing-style.md`) | >= 98.0% | TODO — EvalAgent stub (still not populating `Draft.style_conformance_score`) |

### Latency and Throughput

| Metric | Target | Status |
|--------|--------|--------|
| Ingest-to-triage latency p95 | <= 60s | DONE — measured |
| Ingest-to-triage latency p99 | <= 180s | DONE — measured |
| Draft generation latency p95 | <= 45s | DONE — measured |
| Brief generation completion rate | >= 99.5% | DONE — measured |
| Brief delivery timeliness (within 10 min of window) | >= 99.0% | DONE — measured |

### Undo and Reversibility

| Metric | Target | Status |
|--------|--------|--------|
| Undo success rate (system-initiated mutations) | >= 99.9% | DONE — measured |
| Undo execution latency p95 | <= 30s | DONE — measured |
| Mutation ledger completeness | 100% | DONE — all fields enforced in model |

### Reliability and Operations

| Metric | Target | Status |
|--------|--------|--------|
| Service availability (ingest/triage/draft/brief) | >= 99.9% monthly | TODO |
| Alerting MTTA for sev1+ | <= 10 min | TODO |
| sev1 mitigation start time | <= 20 min | TODO |
| Backup restore drill | 100% pass in staging | TODO |

### Recovery Objectives

| Metric | Target | Status |
|--------|--------|--------|
| RTO (brief/draft pipeline outage) | <= 60 min | TODO |
| RPO (decision/memory/audit stores) | <= 5 min | TODO |

### Cost and Efficiency

| Metric | Target | Status |
|--------|--------|--------|
| Average model cost per active inbox per day | <= $0.75 | DONE — per-call USD cost accounting via `PRICING_USD_PER_1K` in `core/llm/budget.py`; daily Redis rollups; `get_cost_totals()` feeds `/slo/status` |
| Budget overrun guardrail (auto-degradation) | Trigger at 80% of monthly budget | DONE — auto-degradation in `core/llm/budget.py` |
| Cached/reused inference hit rate | >= 40% by end of month 1 | DONE — per-day hit/miss counters in `core/llm/cache.py`; `get_cache_stats()` feeds `/slo/status` |

### Launch Decision Rule

Launch approved only if **all critical gates pass**:
- False-archive rate
- Prompt-injection pass rate
- Undo success rate
- Backup/restore drill
- SLO dashboard operational

Any miss requires explicit waiver by User with documented compensating controls.

---

## Production Readiness Checklist

Final pre-launch verification. All items must be checked.

| # | Check | Status |
|---|-------|--------|
| P.1 | OAuth and token lifecycle tested (expiry/reconnect) | TODO |
| P.2 | No auto-send path exists in code or scopes | DONE |
| P.3 | All worker pipelines idempotent and replay-safe | PARTIAL |
| P.4 | Observability dashboards for ingest/triage/draft/brief | PARTIAL |
| P.5 | Backup and recovery tested for DB and queue state | TODO |
| P.6 | PII-safe logging defaults and redaction policies enabled | TODO |
| P.7 | Compound Engineering release artifacts completed | TODO |
| P.8 | Final PR process passed (PR review checklist) | TODO |
| P.9 | Writing-style policy injection enabled and tested | PARTIAL |
| P.10 | Threat model completed and approved | TODO |
| P.11 | Prompt-injection defenses and safety eval passing | DONE |
| P.12 | Autonomous mutations fully reversible with tested undo | DONE |
| P.13 | SLOs, RTO, RPO documented, instrumented, validated by drill | TODO |
| P.14 | Incident runbooks and on-call escalation verified | PARTIAL |

---

## Timeline Estimates (from plan)

| Milestone | Estimated Duration | Cumulative |
|-----------|-------------------|------------|
| Phase 0 — Foundations | 3–5 days | Week 1 |
| Phase 1 — Gmail Ingestion | 4–6 days | Weeks 1–2 |
| Phase 2 — Triage Engine v1 | 6–8 days | Weeks 3–4 |
| Phase 3 — Drafting in User Voice | 4–6 days | Weeks 5–6 |
| Phase 4 — Brief System | 4–6 days | Weeks 5–7 |
| Phase 5 — Assistant + Memory | 6–9 days | Weeks 5–7 |
| Phase 6 — Reliability + Hardening | 5–7 days | Weeks 8–9 |
| Phase 7 — Acceptance + Launch | 3–4 days | Weeks 8–11 |
| **Total** | **~8–11 weeks** | |

---

## Priority Queue (Recommended Next Steps)

1. ~~**Frontend dashboard** (X.1)~~ — DONE
2. ~~**CI/CD pipeline** (X.4)~~ — DONE
3. ~~**Integration tests on Postgres** (X.5)~~ — DONE
4. **Google Cloud OAuth setup** (X.2) — unblocks real Gmail testing
5. ~~**Threat model document** (H.1–H.4)~~ — DONE (`docs/threat-model.md`)
6. ~~**Data classification policy** (H.5–H.11)~~ — DONE (`docs/data-classification.md`)
7. **Backup/restore drill** (H.19) — launch gate requirement
8. ~~**A/B testing framework** (7.9)~~ — DONE (TriageAgent + DraftAgent + BriefAgent all resolve variants; all 3 primary metrics now produce tagged data)
9. **Gold eval dataset** (7.6) — nightly eval pipeline ready; needs real samples
10. **Staging environment** (X.7) — infrastructure provisioning
11. ~~**Multi-turn assistant state** (X.12)~~ — DONE
12. ~~**Attachment text extraction** (X.11)~~ — DONE

---

*This roadmap should be updated as features are completed or priorities shift.*
