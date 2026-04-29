# Launch Decision Memo — Template

**Status**: template (v1)
**Instantiate as**: `docs/launches/YYYY-MM-DD-launch-memo.md` when approaching
each launch. Commit the instantiated version so the decision is auditable.

---

## Decision

**Decision**: APPROVE | DEFER | REJECT
**Launch window (UTC)**: _______________________
**Rollout mode**: shadow → observe → auto  |  direct to observe  |  direct to auto
**Initial audience**: <internal-only | N specific users | public limited>

**Approver**: _______________________   (operator role)
**Date**: _______________________

---

## What we're launching

A 2–4 sentence description of the user-facing scope. Avoid jargon; this is
what you'd tell a non-engineer reviewer. Link to the roadmap section.

## Why now

What has closed since the last launch / prior deferral that makes this
window viable. Reference specific gate sign-offs and recently-landed
capabilities.

## Quality posture

| SLO | Target | Current (staging, 7d) | Status |
|-----|--------|-----------------------|--------|
| False-archive rate | ≤ 0.5% | ___% | PASS / WARN / FAIL |
| Prompt-injection pass rate | ≥ 99% | ___% | |
| Undo success rate | ≥ 99.9% | ___% | |
| Ingest → triage p95 | ≤ 60 s | ___ s | |
| Draft grounding-failure rate | ≤ 1.5% | ___% | |
| Brief completion rate | ≥ 99.5% | ___% | |
| Brief timeliness | ≥ 99% | ___% | |
| Cache-hit rate | trending ≥ 40% | ___% | |
| Cost per active mailbox / day | ≤ $0.75 | $___ | |

Reference: `/slo/status` or screenshot from the dashboard.

## Risk posture

**Risk register score ≥ 15 items still OPEN**:
- R#: ___ (likelihood × impact = ___)

**Mitigations in place for each**: <paragraph or table>

**Items waived by this launch**: <list with compensating controls>

## Rollback plan

- **Trigger**: <what condition fires a rollback? e.g., sev1 incident,
  false-archive > 1% sustained 1h, critical audit events spike>
- **Execution**: `SHADOW_MODE=true` flips all mutations off within minutes;
  `KILL_SWITCH_LLM=true` removes LLM from every agent path. Both are
  reversible without redeploy.
- **Decision authority**: any on-call responder can pull either kill switch
  without escalation; a deploy rollback needs operator confirmation.
- **Data recovery**: mutation ledger provides 7-day undo for any autonomous
  action; backup/restore drill completed YYYY-MM-DD covers DB corruption.

## Communications

- **Pre-launch notice**: <who gets told, when, via what channel>
- **Status page**: <URL>
- **Post-launch T+0 summary**: drafted in advance as
  `docs/launches/YYYY-MM-DD-launch-summary.md`
- **T+7 retro**: scheduled <date>, responsible <name>

## Waivers explicitly accepted

For each, state the criterion (from `quality-gates.md` or
`release-readiness.md`), the reason, the compensating control, and a
revisit date.

1. _______________________
2. _______________________

## Go/No-go checklist

- [ ] Release readiness (`release-readiness.md`) signed off within 24h of
  this memo
- [ ] All critical SLOs PASS or WAIVED with compensating control
- [ ] Risk register has no OPEN score ≥ 20
- [ ] On-call schedule confirmed for first 2 weeks
- [ ] Rollback drill executed within the last 30 days
- [ ] All approvers have reviewed this memo

---

## Approver Signatures

| Role | Name | Date | Comments |
|------|------|------|----------|
| Operator | | | |
| (optional) Security reviewer | | | |
| (optional) User representative | | | |

---

## Change Log for this launch

Kept in this file, appended post-launch:

- **T+0**: link to deploy run, link to first `/slo/status` after launch.
- **T+24h**: incidents triggered, resolved, open.
- **T+7d**: SLO reality vs. pre-launch projection; any waivers revisited.
- **T+30d**: link to retrospective doc.
