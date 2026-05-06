# Prototype PRD (Phase 1)

## Status
- `status`: active
- `owner`: engineering
- `last_updated`: 2026-04-30

## Scope
- Gmail-only integration.
- Triage + draft + brief core flows.
- Single-tenant pilot.
- Primary persona focus: `Manager/Operator`.

## Success metrics
- Triage precision/recall target: precision ≥85%, recall ≥80%
- Draft acceptance rate target: ≥60% (accepted without major edit)
- Daily triage time reduction target: ≥40% vs. unassisted baseline
- Primary gate metric: Composite score (triage quality + time saved + draft acceptance).
- Composite formula default: `0.40 * triage_quality + 0.35 * time_saved + 0.25 * draft_acceptance`.
- Composite gate pass threshold: composite score ≥ 0.75
- Minimum floor thresholds for each component: triage_quality ≥ 0.72, time_saved ≥ 0.60, draft_acceptance ≥ 0.50
- Pilot design: staged — initial 5-user cohort, expand to 10 after week 1 quality check passes.

## Constraints
- No autonomous send/delete.
- Minimal connectors only.
- Automation authority is `drafts + labeling only`.
- No external side-effect actions beyond approved label/draft operations.
- Formal compliance certification is out-of-scope for Prototype; evidence collection is in-scope.
- Baseline data retention policy: retain raw artifacts for 30 days by default.
- Performance/eval coverage must include tiered inbox volume cohorts (20-400 emails/day/user).

## Ticket linkage
- Source of truth tickets: `../tickets/prototype-tickets.md`

## Gate criteria
- Must satisfy Prototype gate in `../reviews/phase-gates.md`.
