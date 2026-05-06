# Inbox Chief of Staff Global Execution Roadmap

## Purpose
This is the master execution tracker for building the Inbox Chief of Staff system end-to-end.  
It combines PRD flow, engineering execution workflows, ticket governance, QA/eval gates, security/compliance controls, deployment, and approval sequencing.

Use this file as the primary operational reference during execution.

## Scope and target outcome
- Build a Cora-class inbox chief-of-staff product using a lightweight architecture.
- Implement a verticalized multi-agent system governed by an orchestrator.
- Add RAG grounding for personalization and safer generation in later phases.
- Deploy frontend on Vercel and backend infrastructure with low-cost, minimal connectors.
- Optimize the first shipped experience for the `Manager/Operator` persona.
- Enforce initial automation authority as `drafts + labeling only`.
- Use mixed-tier performance assumptions for inbox volume (20-400 emails/day/user tiers).
- Do not enforce a strict per-user cost cap initially; prioritize quality and robustness first.

## Canonical references
- Plan: `/Users/neelmishra/.cursor/plans/inbox_chief_of_staff_build_plan_6b5b2984.plan.md`
- Product research: `/Users/neelmishra/.cursor/Rula/inbox-chief-of-staff/research/product-context-synthesis.md`
- PRDs: `prds/prototype-prd.md`, `prds/mvp-prd.md`, `prds/production-prd.md`
- Tickets: `tickets/prototype-tickets.md`, `tickets/mvp-tickets.md`, `tickets/production-tickets.md`
- Gate approvals: `reviews/phase-gates.md`
- Connectors/env vars: `architecture/connectors-apis-env.md`
- Frontend architecture outputs: `architecture/frontend/`
- Backend architecture outputs: `architecture/backend/`
- Execution runbook: `runbooks/execution-runbook.md`

## Non-negotiable phase sequencing
- Do not start MVP implementation until Prototype Gate 1 is approved.
- Do not start Production implementation until MVP Gate 2 is approved.
- P1 tickets must be complete to pass each phase.
- Any unresolved critical safety/security issue blocks progression.
- All frontend architecture artifacts must be written in `architecture/frontend/`.
- All backend architecture artifacts must be written in `architecture/backend/`.
- No autonomous send, delete, or external side-effect actions in any phase unless explicitly approved in a later PRD revision.

## Delivery architecture baseline (execution target)

### Core system workflow
1. Ingest new email from Gmail connector.
2. Normalize and validate message schema.
3. Route message to orchestrator.
4. Orchestrator dispatches to specialized subagents:
   - Triage agent
   - Draft agent
   - Brief agent
   - Follow-up agent
   - Policy/compliance guard
5. RAG layer retrieves user-specific context for grounded decisions.
6. Policy guard enforces action restrictions and confidence gates.
7. Action outputs flow to review UI and safe execution channels.
8. Telemetry and eval harness capture outcomes and feed feedback loop.

### Launch priority policy (manager/operator)
- Use hybrid importance scoring:
  - sender tier importance
  - SLA/commitment state
  - urgency/deadline signal extraction

### UX execution workflow
1. Define user archetypes and journey map in each phase.
2. UX agent outputs wireflow and interaction map.
3. UI agent maps wireflow to design-system components.
4. Frontend implements approved UX contracts only.
5. Usability findings feed next PRD and ticket updates.
6. Manager/Operator-first UX is mandatory until Gate 2 (MVP exit) is approved.

### Data and governance workflow
1. Collect synthetic + authorized pilot datasets.
2. Version eval datasets and test scenarios.
3. Run offline and online evals continuously.
4. Log incidents, root causes, and mitigation actions.
5. Compound learnings into updated tests/rules/runbooks.
6. Apply default retention policy: raw artifacts retained 30 days, metadata retained per audit requirements.

## Infrastructure execution workflow

### Frontend deployment path
- Platform: Vercel
- Build workflow:
  1. Implement Next.js app surfaces (triage feed, draft queue, brief reader, settings).
  2. Validate with unit/integration/UI tests.
  3. Deploy preview environments per PR.
  4. Promote to production only after phase gate approval.

### Backend deployment path
- Recommended lightweight stack: Cloud Run + Cloud SQL Postgres (pgvector) + Cloud Tasks + GCS.
- Build workflow:
  1. Stand up API service and worker service.
  2. Configure queue-driven asynchronous workflows.
  3. Add observability and audit logging.
  4. Enforce policy guardrails and safety controls.
  5. Roll out by environment (dev -> staging -> production).

## Connectors/API rollout workflow

### Prototype allowed connectors only
- Gmail API/OAuth
- One primary LLM provider (optional fallback provider)
- Postgres/pgvector
- Queue provider
- Object storage
- Basic observability
- Volume testing must cover tiered loads (`20-50`, `50-150`, `150-400` emails/day/user).

### MVP additions (only after Gate 1)
- Multi-tenant auth/session provider
- Embedding provider and RAG tuning controls
- Billing provider
- Feature flag provider

### Production additions (only after Gate 2)
- Incident alerting/SIEM integrations
- Backup/DR integrations
- Optional Outlook integration only if explicitly approved

### Connector minimization policy
- Every connector must map to an approved ticket and measurable user value.
- New connector requires owner, cost estimate, risk note, rollback plan.

## Quality, testing, and evaluation workflow

### Continuous test layers
- Unit tests: agent logic, validators, contracts.
- Integration tests: connector + orchestration + storage pathways.
- End-to-end tests: inbox event to user review output.
- Security tests: auth boundaries, scopes, policy enforcement.
- Reliability tests: retries, idempotency, queue failure handling.

### Eval program
- Agent evals: triage accuracy, draft quality, brief relevance.
- Workflow evals: handoff correctness and state transitions.
- Safety evals: policy violations, PII handling, unauthorized actions.
- Product evals: time saved, miss rate, edit distance, trust score.

### Prototype composite gate metric (primary gate signal)
- Composite score formula:
  - `Composite = 0.40 * triage_quality + 0.35 * time_saved + 0.25 * draft_acceptance`
- Gate 1 pass condition:
  - Composite score meets agreed threshold in pilot window.
  - No single component can be below its minimum floor threshold.

### Gate evidence package (required)
- Test reports
- Eval scorecards vs baseline
- Incident/risk summary
- Ticket completion snapshot
- Approval recommendation

## Security and compliance execution workflow
- Enforce least privilege and minimal OAuth scopes.
- Apply encryption in transit/at rest and secrets management.
- Record auditable action logs for all agent decisions.
- Maintain retention/deletion controls and DSAR readiness.
- Progress compliance maturity by phase (MVP baseline, Production hardening).
- Formal compliance certification is deferred for initial production release; maintain certification-ready evidence trails during implementation.

## Safety controls workflow (production-critical)

### Circuit breaker
- Detect anomalous behavior (error spikes, misclassification spikes, policy violations).
- Trigger automatic degraded mode.
- Pause high-risk automated behaviors until recovery criteria pass.

### Kill switch
- Global and tenant-level immediate stop control.
- Audited activation and recovery.
- Verified through scheduled drills before launch approval.

## Phase-by-phase execution plan and tracker

## Phase 1: Prototype (5 weeks)

### Objectives
- Prove core user value with triage + draft + brief.
- Validate orchestrator and subagent contracts.
- Establish baseline eval and telemetry.

### Execution workflow
- Week 1:
  - Finalize Prototype PRD.
  - Lock user archetypes and UX map.
  - Approve architecture baseline and connector list.
- Week 2-3:
  - Execute Prototype P1 tickets in `tickets/prototype-tickets.md`.
  - Implement ingestion -> orchestrator -> triage/draft/brief flow.
- Week 4:
  - Implement review UI, telemetry, eval harness.
  - Add feedback controls and policy guard P2 where feasible.
- Week 5:
  - Pilot/UAT, bug fixing, and gate package preparation.

### Required gate (Gate 1)
- All Prototype P1 tickets: done
- Prototype tests: pass
- Eval thresholds: met using composite gate formula
- Critical policy/safety issues: none open
- Pilot sign-off: complete via staged pilot (start 5-10 users, expand after week 1 quality check)

### Progress tracker
- Phase status: `in_progress`
- Planned start: 2026-04-30
- Planned end: 2026-06-04
- Actual start: 2026-04-30
- Actual end: TBD
- % complete: 60%
- P1 tickets: 9/9 done (all backend + frontend scaffold complete; backend 17/17 tests pass; frontend tsc exits 0)
- Remaining: pilot/UAT window, eval data collection, composite gate metric measurement
- Risks/blockers: None currently

## Phase 2: MVP (7 weeks)

### Objectives
- Add multi-tenancy and RAG v1.
- Improve reliability and policy controls.
- Prepare for controlled beta.

### Execution workflow
- Week 1:
  - Finalize MVP PRD using prototype findings.
  - Re-prioritize MVP tickets.
- Week 2-4:
  - Execute MVP P1 tickets in `tickets/mvp-tickets.md`.
  - Implement multi-tenant auth, RAG v1, policy guard v2, queue reliability.
- Week 5-6:
  - Build admin dashboard, onboarding improvements, billing, eval automation.
- Week 7:
  - Run beta validation and prepare Gate 2 package.

### Required gate (Gate 2)
- All MVP P1 tickets: done
- Reliability/security tests: pass
- Eval delta vs Prototype: improved
- Beta runbook and support readiness: validated

### Progress tracker
- Phase status: `blocked_until_gate_1`
- Planned start: TBD
- Planned end: TBD
- Actual start: TBD
- Actual end: TBD
- % complete: 0%
- Risks/blockers: TBD

## Phase 3: Production (8 weeks)

### Objectives
- Harden for production reliability, compliance, and operational safety.
- Deploy with circuit breaker, kill switch, DR readiness, and canary rollout.

### Execution workflow
- Week 1:
  - Finalize Production PRD with risk/compliance review.
- Week 2-5:
  - Execute Production P1 tickets in `tickets/production-tickets.md`.
  - Implement RAG v2 safety, compliance controls, observability, security hardening.
- Week 6:
  - Run DR, kill switch, and circuit breaker drills.
- Week 7-8:
  - Execute canary rollout and launch-readiness review.

### Required gate (Gate 3)
- All Production P1 tickets: done
- Regression/security/compliance checks: pass
- Circuit breaker + kill switch drills: pass
- Canary success criteria: met
- Rollback readiness: verified

### Progress tracker
- Phase status: `blocked_until_gate_2`
- Planned start: TBD
- Planned end: TBD
- Actual start: TBD
- Actual end: TBD
- % complete: 0%
- Risks/blockers: TBD

## Global ticket and execution tracker

### Ticket file ownership
- Prototype: `tickets/prototype-tickets.md`
- MVP: `tickets/mvp-tickets.md`
- Production: `tickets/production-tickets.md`

### Update policy for coding agent
- Update ticket status on every meaningful change.
- Record blockers with date and dependency.
- Link evidence (PR/tests/evals) before marking done.
- Reflect phase-level changes in this roadmap progress tracker.

## Gate approval tracker

### Gate 0 (Prototype entry)
- Status: approved
- Approver: Neel Mishra
- Date: 2026-04-30

### Gate 1 (Prototype exit -> MVP entry)
- Status: pending
- Approver: TBD
- Date: TBD

### Gate 2 (MVP exit -> Production entry)
- Status: pending
- Approver: TBD
- Date: TBD

### Gate 3 (Production launch)
- Status: pending
- Approver: TBD
- Date: TBD

## Reporting cadence
- Daily: ticket updates, blocker log, risk notes.
- Weekly: phase progress summary, eval trends, quality status.
- Gate week: formal approval packet and go/no-go recommendation.
- Initial production incident target: P1 acknowledged within 1 hour.

## Definition of done (global)
- Target phase P1 scope is complete.
- Required quality/security/eval evidence is attached.
- Gate is approved in `reviews/phase-gates.md`.
- Compounding artifacts are captured for next phase planning.
