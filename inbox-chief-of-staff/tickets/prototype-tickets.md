# Prototype Engineering Tickets (Phase 1)

## Usage
- Update each ticket fields as work progresses.
- Status values: `todo`, `in_progress`, `blocked`, `done`.
- P1 must all be `done` for phase gate pass.
- Persona optimization target for Phase 1: `Manager/Operator`.
- Automation authority for Phase 1: `drafts + labeling only`.

## P1 Tickets

### ICE-P1-001 Gmail OAuth + Ingestion
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: none
- Deliverable: OAuth flow + message ingestion endpoint + webhook handling
- Evidence links: backend/app/ingestion/gmail_client.py, backend/app/ingestion/webhook_handler.py, backend/app/api/routes/auth.py, backend/app/repositories/user_repo.py
- Blockers: none

### ICE-P1-002 Message Normalization + Validation
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: ICE-P1-001
- Deliverable: normalized schema + validation rules + error handling
- Evidence links: backend/app/ingestion/normalizer.py, backend/tests/test_ingestion/test_normalizer.py (4/4 tests pass)
- Blockers: none

### ICE-P1-003 Orchestrator State Machine
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: ICE-P1-002
- Deliverable: workflow handoffs for triage/draft/brief
- Evidence links: backend/app/orchestrator/state_machine.py, backend/app/orchestrator/agent_dispatcher.py
- Blockers: none

### ICE-P1-004 Triage Agent v1
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: ICE-P1-003
- Deliverable: classification + confidence scoring + deterministic fallback
- Evidence links: backend/app/agents/triage_agent.py, backend/tests/test_agents/test_triage_agent.py (3/3 tests pass)
- Blockers: none

### ICE-P1-005 Draft Agent v1
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: ICE-P1-003
- Deliverable: draft generation in user voice (draft-only)
- Evidence links: backend/app/agents/draft_agent.py
- Blockers: none

### ICE-P1-006 Brief Agent v1
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: ICE-P1-003
- Deliverable: morning/afternoon digest generation
- Evidence links: backend/app/agents/brief_agent.py
- Blockers: none

### ICE-P1-007 Review UI Core
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: ICE-P1-004, ICE-P1-005, ICE-P1-006
- Deliverable: priority inbox, draft review queue, brief reader
- Evidence links: frontend/src/components/inbox/TriageFeed.tsx, frontend/src/components/inbox/MessageCard.tsx, frontend/src/components/drafts/DraftCard.tsx, frontend/src/components/brief/BriefReader.tsx, frontend/src/app/(app)/, frontend/src/lib/api-client.ts — `tsc --noEmit` exits 0
- Blockers: none

### ICE-P1-008 Telemetry + Eval Harness v1
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: ICE-P1-003
- Deliverable: event logging + baseline eval pipeline
- Evidence links: backend/app/telemetry/events.py, backend/app/telemetry/eval_harness.py, backend/app/repositories/eval_repo.py, backend/app/repositories/audit_repo.py
- Blockers: none

### ICE-P1-009 Action Policy Matrix Enforcement
- Priority: P1
- Status: done
- Owner: engineering
- Due: 2026-05-14
- Completed: 2026-04-30
- Dependencies: ICE-P1-003
- Deliverable: enforce allowed actions (draft + label only), block send/delete/other side effects, and log policy decisions
- Evidence links: backend/app/policy/action_policy.py, backend/tests/test_policy/ (10/10 tests pass)
- Blockers: none

## P2 Tickets

### ICE-P2-010 Feedback Controls
- Priority: P2
- Status: todo
- Owner: TBD
- Due: TBD
- Dependencies: ICE-P1-007
- Deliverable: user feedback actions for triage and tone correction
- Evidence links: TBD
- Blockers: none

### ICE-P2-011 Policy Guard v1
- Priority: P2
- Status: todo
- Owner: TBD
- Due: TBD
- Dependencies: ICE-P1-003
- Deliverable: rule checks for restricted actions and policy tags
- Evidence links: TBD
- Blockers: none

## P3 Tickets

### ICE-P3-012 Follow-up Extraction v0
- Priority: P3
- Status: todo
- Owner: TBD
- Due: TBD
- Dependencies: ICE-P1-004
- Deliverable: extract commitments and candidate follow-up reminders
- Evidence links: TBD
- Blockers: none
