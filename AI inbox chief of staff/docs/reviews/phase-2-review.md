# Phase 2 Review Packet — Triage Engine v1

**Status**: v1
**Companions**: `../PRODUCT_ROADMAP.md`, `../quality-gates.md`, `../risk-register.md`

---

## Header

| Field | Value |
|-------|-------|
| Phase | 2 — Triage Engine v1 |
| Packet date | 2026-04-25 |
| Author | `<owner>` |
| Reviewers | `<names>` |
| Roadmap snapshot SHA | `<git sha>` |
| Related risks | R3 (gold-eval gap), R4 (prompt injection), R7 (LLM circuit) |

---

## 1. Phase Scope

| Roadmap ID | Feature | Status | Evidence |
|------------|---------|--------|----------|
| 2.1 | Deterministic rule engine | PASS | `subagents/triage.py` AlwaysInbox, Newsletter, DirectReply rules |
| 2.2 | LLM classifier fallback | PASS | `TriageAgent._llm_classify()` |
| 2.3 | Confidence scoring + fallback handling | PASS | `core/config.py::triage_*_threshold` |
| 2.4 | Retrieval of similar past emails for triage context | PASS | `TriageAgent._retrieve_similar_emails()` pgvector cosine |
| 2.5 | Memory-informed triage | PASS | mailbox + user-global memories injected into rules + LLM |
| 2.6 | Triage correction feedback loop | PASS | `api/routers/feedback.py` correction → memory update |
| 2.7 | Protected sender/thread/category rules | PASS | `AlwaysInboxRule` consumes `always_inbox` memories from mailbox UI |
| 2.8 | Per-mailbox rate limiting (Gmail API + LLM tokens) | PASS | `core/gmail/rate_limiter.py` + `core/llm/budget.py` |

---

## 2. Gate Criteria

| # | Criterion | Verification | Status |
|---|-----------|--------------|--------|
| 2.a | Rule-engine precedence + unit coverage | `tests/unit/test_triage_rules.py` — 12 tests | PASS |
| 2.b | LLM fallback path on provider error | deterministic-fallback path; unit-tested | PASS |
| 2.c | Confidence thresholds configurable + tested | `core/config.py::triage_*_threshold` + assert | PASS |
| 2.d | False-archive eval sample on ≥ 100 real emails | pending gold dataset | BLOCKED — R3 |
| 2.e | Memory-informed triage | `MemoryAgent` + `TriageAgent._retrieve_similar_emails` integration | PASS |

---

## 3. Acceptance Evidence

- **Tests**: `pytest tests/unit/test_triage_rules.py tests/unit/test_triage_agent.py tests/safety/` — 12 + `<N>` triage + 17 safety = `<total>` passing on commit `<sha>`
- **Migrations**: 002 (pgvector embedding columns on `emails`, `memories`) + 003+ (memory + audit triggers)
- **A/B framework**: Phase 7 wiring (item 7.9) already routes triage variants — Phase 2 outputs are tagged with variant for downstream rollup
- **Dashboards**: `/slo/status` exposes false-archive rate measurement over `mutation_ledger`
- **PRs merged into main during this phase**: `<PR# range>`

---

## 4. Risk Delta

| Risk ID | Title | Pre-phase status | Post-phase status | Notes |
|---------|-------|------------------|-------------------|-------|
| R3 | Real gold-eval dataset gap | n/a | OPEN | Pipeline scaffolding landed in Tier-1 sweep; dataset itself populated post-OAuth |
| R4 | Prompt injection escaping defenses | n/a | OPEN | Synthetic suite at 100%; PDF/Unicode adversarial fixtures still TBD |
| R7 | LLM provider circuit-breaker cascade | n/a | OPEN | Per-provider isolation in place; multi-region fallback deferred |

No new risks introduced this phase beyond those already in the register.

---

## 5. Outstanding Items / Waivers

### Waiver: 2.d — False-archive eval on ≥ 100 real emails
- **Reason**: A representative gold dataset cannot be built without
  read-only access to a real mailbox (R3). Synthetic adversarial
  coverage (`tests/safety/`) is at 100% and the live `false_archive_rate`
  measurement over `mutation_ledger` is wired into `/slo/status`.
- **Compensating control**: Gold-eval pipeline scaffolding (migration 007
  + `core/gold_eval/*` + `workers/gold_sample_extraction.py` + admin
  router) is merged behind feature flag `gold_sampling_enabled`. Sample
  extraction fires the day Gmail OAuth lands. Until then, the production
  `/slo/status` measurement gates Gate 7, not a static dataset.
- **Revisit date**: 7 days after first real-mailbox sample is labelled
  (target ≥ 100 across strata).
- **Owner**: `<owner>`
- **Tracked in**: `risk-register.md::R3`, roadmap item 7.6.

---

## 6. Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineering | `<owner>` | `2026-04-25` | _______________ |
| Product / Owner | `<owner>` | `2026-04-25` | _______________ |

I confirm every PASS row in §2 has verifiable evidence in §3. The single
non-PASS row (2.d BLOCKED) carries a waiver in §5 gated on R3, with a
compensating control (live-traffic measurement + scaffolded fixture
pipeline). Phase 2 is **conditionally closed**: synthetic + live-metric
sign-off granted; gold-dataset eval re-validation required before Gate 7.

---

## Change Log

- `2026-04-25 (v1)`: Phase 2 closed conditionally pending R3 resolution.
  All code paths PASS; gold-dataset eval defers to post-OAuth sample run.
