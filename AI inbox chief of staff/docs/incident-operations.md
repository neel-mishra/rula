# Incident Operations

**Status**: v1
**Scope**: Severity matrix, response SLAs, on-call routing, post-incident
review process. Covers `H.21` + `H.26` + `H.27` from the roadmap.

This document is the operator's runbook for "something's wrong in prod."
It pairs with the technical runbooks in `runbooks/` and the risk register.

---

## 1. Severity Matrix  (H.21)

| Sev | Definition | Example | MTTA target | Mitigation-start target | Comms cadence |
|-----|-----------|---------|-------------|-------------------------|---------------|
| **sev0** | Total product outage or active data-integrity incident | RDS unreachable; all triage stopped; silent wrong archive detected in prod | 5 min | 15 min | Every 15 min until stable |
| **sev1** | Major feature broken for all or most users, OR security-impacting event | All drafts failing grounding; circuit breaker tripped on both LLM providers; OAuth refresh failing system-wide | 10 min | 20 min | Every 30 min |
| **sev2** | Partial degradation; one subsystem impaired; SLO breach | Brief delivery timeliness dropped below 99%; DLQ accumulating faster than replay | 30 min | 2 hr | On mitigation start + close |
| **sev3** | Low-impact issue, workaround exists | Single mailbox stuck; cosmetic UI bug | 4 hr business-hours | Next business day | On close |

**MTTA** = Mean Time To Acknowledge (responder claims the page).
**Mitigation start** = a human is actively working on reducing impact.

Rule of thumb: if you're unsure between two sevs, pick the higher one for the
first 15 minutes, then re-classify once scope is known.

---

## 2. On-Call Routing  (H.26)

Current setup uses the alert router in `core/alerts/` with two sinks:

- **Slack** — `slack_webhook_url` setting. All severities post here.
- **PagerDuty** — `pagerduty_routing_key` setting. Only `CRITICAL` severity
  triggers a page; `WARNING` and `INFO` are dropped at the sink (see
  `core/alerts/sinks.py::PagerDutySink.send`).

### Auto-paging events (wired in code today)
- LLM circuit breaker trip (`core/llm/circuit_breaker.py::_ProviderState.record_failure`)
- DLQ replay errors (`workers/dlq_replay.py::replay_dlq`)

### Not yet auto-paged (manual escalation)
- RDS down (needs CloudWatch alarm → SNS → PagerDuty — infra work)
- Ingest queue backlog (needs CloudWatch alarm on queue depth)
- False-archive SLO breach (needs periodic `/slo/status` evaluator)

When infra is provisioned, add CloudWatch alarms feeding the same
`pagerduty_routing_key` so the surface stays consistent.

### Acknowledgement
- Slack: react with :eyes: on the alert post within MTTA target.
- PagerDuty: acknowledge via the mobile app or email.
- After ack, respond in the `#incident-<sev>-<shortid>` channel (create if
  absent) with status every comms-cadence interval.

---

## 3. First-Responder Checklist

When you acknowledge an alert:

1. **Verify the blast radius** — is this one user, one mailbox, one
   subsystem, or global? Hit `/admin/activity-stats` to see if multiple
   users are affected.
2. **Check the kill switches** before doing anything else — a fast way to
   reduce blast radius without a code change:
   - `KILL_SWITCH_LLM=true` stops all LLM calls; agents fall back to
     deterministic rules.
   - `SHADOW_MODE=true` skips all mutations and Gmail writes.
3. **Open the relevant runbook**:
   - Gmail webhook/watch failure → `runbooks/gmail-watch-failure.md`
   - Model provider outage → `runbooks/model-provider-outage.md`
   - False-archive spike → `runbooks/false-archive-spike.md`
   - Anomalous draft behavior → `runbooks/anomalous-draft.md`
4. **Communicate** — post initial status in the incident channel within 5
   minutes of ack. Include: what you know, what you've tried, ETA for next
   update.
5. **Preserve evidence** — before rolling back or restarting, capture:
   - Correlation IDs from the triggering logs (every stage log carries one).
   - The last 5 minutes of `audit_events` for the affected mailbox(es).
   - The mutation-ledger rows that bracket the incident.

---

## 4. Post-Incident Review (PIR) Process  (H.27)

Trigger a PIR for any sev0 or sev1, and for any sev2 that breached an SLO
for more than the comms cadence. Sev3 does not require a PIR unless the
responder requests one.

### Cadence
- **T+0** (incident close): timestamped timeline captured in the incident
  channel is frozen as the PIR draft — do not delete the channel for 30
  days.
- **T+1 to T+2 days**: PIR author (the first responder by default) fills
  out the PIR template below.
- **T+3 days**: Synchronous review with operator + any contributors; at
  least one action item must be assigned + dated.
- **T+30 days**: Action-item closure check. Unresolved items feed back into
  the risk register.

### PIR Template

```markdown
# Incident: <short title>

**Date**: YYYY-MM-DD
**Duration**: HH:MM to HH:MM (UTC)
**Severity**: sev0 | sev1 | sev2 | sev3
**Responder(s)**: <names>
**User impact**: <affected user count, affected feature(s)>

## Timeline
<UTC timestamp> — what happened (observed / acted)

## What went wrong
Root cause. Prefer mechanism ("the LLM cache key didn't include the prompt
version, so v2-ed drafts pulled v1 cached responses") over blame.

## What went right
Keep this — process + tool improvements compound when we reinforce what
worked.

## Contributing factors
Conditions that made the failure more likely. Distinct from root cause.

## Action items
- [ ] <action> — owner: <name> — due: YYYY-MM-DD — ref: #<issue>
- [ ] ...

## Follow-up links
- Risk register row(s) updated: <R#>
- Runbook(s) changed: <path>
- Code changes: <PR #s>
```

### Principles
- **Blameless** — the goal is to harden the system, not assign fault.
- **Action items map to code or process** — "be more careful" is not an
  action item; "add PR check that rejects migrations without downgrade" is.
- **Link back to the risk register** — every PIR should either close out an
  existing risk or add a new one.

---

## 5. Scheduled Operations (not incidents, but same muscle)

| Operation | Cadence | Owner |
|-----------|---------|-------|
| Backup/restore drill (H.19) | Quarterly | Neel |
| Adversarial prompt-injection re-run | On model version change | Neel |
| Risk-register review | Weekly pre-launch, monthly post-launch | Neel |
| Secret rotation (`APP_SECRET_KEY`, KMS keys) | Annually + on incident | Neel |
| Provider zero-retention mode verification | Quarterly | Neel |

---

## 6. Change Log

- **2026-04-24 (v1)**: Initial document covering severity matrix, on-call
  routing tied to the in-code alert sinks, first-responder checklist, PIR
  process + template, and recurring-operations calendar.
