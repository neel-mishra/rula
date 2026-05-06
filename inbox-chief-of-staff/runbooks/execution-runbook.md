# Execution Runbook

## Daily operating loop
1. Pull next ticket from current phase file in `../tickets/`.
2. Move status to `in_progress`.
3. Implement and validate.
4. Attach evidence links.
5. Move status to `done` or `blocked` with blocker details.

## Weekly operating loop
1. Review phase ticket health.
2. Review quality metrics and eval trends.
3. Update risks and mitigations.
4. Prepare gate package in `../reviews/phase-gates.md`.

## Evidence requirements per ticket
- Code change reference (commit/PR link)
- Test results
- Eval results (where applicable)
- Security/compliance checks (where applicable)

## Escalation rules
- Any P1 blocker: escalate immediately and update gate risk note.
- Repeated P2 delays in same domain: escalate to planning review.
- Any safety/control regression: pause phase progression until resolved.
- Production operations target: acknowledge P1 incidents within 1 hour.
