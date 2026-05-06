# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this workspace is

Planning and governance workspace for the **Inbox Chief of Staff** product (Cora-class email triage + draft + brief assistant). There is **no source code here yet** — only markdown artifacts that gate the build. Implementation has not started; treat this directory as the source of truth for PRDs, tickets, gates, architecture decisions, and runbooks.

There are no build/test/lint commands. Work in this repo is editing markdown to plan, prioritize, and record gate decisions.

## Mandatory reading order before doing anything

The README enforces this order — follow it:

1. `inbox-chief-of-staff-plan.md` — canonical implementation context. Read this first; it defines the multi-agent + RAG architecture, build profiles, connector minimization policy, and phase-gate rules.
2. `prds/prototype-prd.md`, `prds/mvp-prd.md`, `prds/production-prd.md` — phase PRDs (in order).
3. `roadmap.md` — master execution tracker, cross-references all artifacts.
4. `tickets/<phase>-tickets.md` — only the current phase's file.
5. `reviews/phase-gates.md` — gate state.

## Phase gating is strict — do not cross phase boundaries

Three sequential phases: **Prototype → MVP → Production**. Rules that override any other instinct:

- Do **not** start MVP work until **Gate 1** is approved in `reviews/phase-gates.md`.
- Do **not** start Production work until **Gate 2** is approved.
- Every **P1** ticket in a phase must be `done` before that phase's gate can pass. P2 deferral requires owner + due date + risk note + explicit approval. P3 goes to backlog unless promoted.
- If asked to work on something from a later phase, flag it and stay in the current phase unless the user explicitly overrides.

Gate 1 pass condition uses a **composite metric**, not a single threshold:
`Composite = 0.40 * triage_quality + 0.35 * time_saved + 0.25 * draft_acceptance`, **and** no component below its individual floor.

## Non-negotiable product/scope rules

These are easy to violate by accident — check before suggesting features or tickets:

- **Automation authority through Phase 1 is `drafts + labeling only`.** No autonomous send, delete, or external side-effect actions in any phase unless a later PRD revision explicitly grants it. Any ticket implying otherwise is out of scope.
- **Phase 1 is Gmail-only, single-tenant.** Outlook is a P3 *discovery spike* in MVP and a P2 *optional* in Production — never assume it's in scope.
- **Persona priority is `Manager/Operator` until Gate 2 passes.** UX trade-offs resolve toward this persona; do not optimize for Executive/EA/IC archetypes first.
- **Connector minimization policy.** Prototype is locked to: Gmail, one LLM provider (+ optional fallback), Postgres/pgvector, queue, object storage, basic observability. Adding a connector requires user-value justification, cost estimate, owner, and rollback path — not just a code change.
- **Volume tiers** for eval/perf coverage: 20–50, 50–150, 150–400 emails/day/user. Don't default to a single load profile.

## Where artifacts go (matters for review tooling)

- Frontend architecture deliverables → `architecture/frontend/` (only).
- Backend architecture deliverables → `architecture/backend/` (only).
- ADRs (when architecture changes) → `architecture/adrs/` as new files; never edit prior decisions in place.
- Gate decisions in `reviews/phase-gates.md` are **append-only with dates** — do not overwrite history.

## Ticket update protocol

Tickets in `tickets/*.md` are living trackers. When changing a ticket:

- Status values: `todo` | `in_progress` | `blocked` | `done`. No other values.
- Move to `done` only when **evidence link** is attached (PR/commit, test output, eval report). A done ticket without evidence does not count toward the gate.
- `blocked` requires date + dependency note.
- Reflect phase-level changes back in `roadmap.md` progress tracker.

## Recommended infra target (for any architecture writing)

The plan's lightweight default is **Vercel (frontend) + Cloud Run (backend/workers) + Cloud SQL Postgres with pgvector + Cloud Tasks + GCS**. Use this as the baseline assumption unless writing a comparison ADR.

## What NOT to do here

- Don't scaffold source code, package manifests, or CI configs in this directory. The plan calls for code to live elsewhere; this workspace stays planning-only.
- Don't invent metrics, owners, dates, or thresholds where artifacts say `TBD` — leave them `TBD` and flag to the user that they need a decision.
- Don't merge or reorder phase artifacts to "simplify" — the phase separation is the governance mechanism.
