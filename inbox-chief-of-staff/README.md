# Inbox Chief of Staff Workspace

This directory is the canonical workspace for planning and executing the Inbox Chief of Staff system.

## Execution order for coding agents
1. Read `inbox-chief-of-staff-plan.md` (canonical implementation context plan).
2. Read `prds/prototype-prd.md`, `prds/mvp-prd.md`, `prds/production-prd.md`.
3. Read `roadmap.md`.
4. Execute tickets in `tickets/` by phase.
5. Record gate outcomes in `reviews/`.
6. Keep architecture and operations docs updated in `architecture/` and `runbooks/`.

## Folder map
- `research/`: product context, user research, references.
- `prds/`: phase PRDs and version history.
- `tickets/`: prioritized engineering tickets with progress tracking.
- `reviews/`: phase-gate approvals, QA outcomes, risk decisions.
- `architecture/`: system design, connectors, APIs, env vars, ADRs.
- `runbooks/`: deploy, incident, rollback, and operational procedures.

## Progress policy
- Every ticket has a status (`todo`, `in_progress`, `blocked`, `done`).
- P1 tickets must be complete before a phase can pass.
- Each completed ticket must link to evidence (PR, test output, eval report).
