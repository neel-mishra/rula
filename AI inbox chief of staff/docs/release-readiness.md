# Release Readiness Checklist

**Status**: v1
**Scope**: Pre-launch verification. Fill in by the operator 72 hours before
the intended launch date.
**Consumed by**: `launch-decision-memo-template.md`.

Every item is either `PASS`, `FAIL`, or `WAIVED`. `WAIVED` requires a
pointer to the compensating control per `quality-gates.md` rules.

---

## 1. Code + Test
- [ ] `pytest tests/` green on the release commit (baseline 187+ tests)
- [ ] Frontend `next build` green on the release commit
- [ ] Adversarial prompt-injection suite ≥ 99% pass (`tests/safety/`)
- [ ] No new `gmail.send` scope; `tests/unit/test_security.py` asserts pass
- [ ] Unit + integration coverage not regressed vs. previous release

## 2. Infrastructure
- [ ] Terraform applied successfully to staging + production
- [ ] RDS: encryption at rest confirmed, automated backups enabled
- [ ] KMS keys provisioned, policies reviewed, rotation scheduled
- [ ] Secrets Manager populated (no plaintext secrets in env)
- [ ] ECS services healthy in both environments
- [ ] CloudWatch alarms wired to PagerDuty routing key

## 3. Connectors
- [ ] Google Cloud OAuth consent screen approved for intended audience
- [ ] Gmail API quota + push subscription provisioned
- [ ] Anthropic production API key with zero-retention mode verified
- [ ] OpenAI production API key with zero-retention mode verified
- [ ] SES domain verified, reputation warmed for brief send
- [ ] SES inbound rule set active, `ses_inbound_secret` populated
- [ ] Slack incoming webhook URL configured
- [ ] PagerDuty routing key configured + test event acknowledged

## 4. Security + Compliance
- [ ] Threat model (`threat-model.md`) reviewed, residual-risks section current
- [ ] Data classification policy (`data-classification.md`) reviewed
- [ ] Verified deletion path tested in staging (`data-classification.md` §8)
- [ ] No Class A/B data in any configured log or alert sink
- [ ] PII scrubber active on all structlog pipelines
- [ ] Privacy notice and terms published; link included in OAuth consent

## 5. Launch-SLO Gates (critical)
- [ ] False-archive rate ≤ 0.5% over a ≥ 7-day staging window with real mail
- [ ] Prompt-injection pass rate ≥ 99.0%
- [ ] Undo success rate ≥ 99.9%
- [ ] Backup/restore drill passed in staging within the last 30 days (see `docs/backup-restore-drill.md`)
- [ ] `/slo/status` reports `launch_ready=true`

## 6. Launch-SLO Gates (non-critical, monitor)
- [ ] Draft grounding-failure rate ≤ 1.5%
- [ ] Ingest-to-triage p95 ≤ 60 s, p99 ≤ 180 s
- [ ] Draft generation p95 ≤ 45 s
- [ ] Brief generation completion ≥ 99.5%, timeliness ≥ 99%
- [ ] Undo execution p95 ≤ 30 s
- [ ] Cache-hit rate trending toward ≥ 40% by end of month 1
- [ ] Average cost / active inbox / day ≤ $0.75

## 7. Operations
- [ ] Runbooks reviewed by a non-author (`runbooks/*.md`)
- [ ] Incident-operations doc (`incident-operations.md`) current
- [ ] On-call rotation scheduled for the first 2 weeks post-launch
- [ ] Risk register (`risk-register.md`) has no OPEN items with score ≥ 20
- [ ] PIR process understood by at least two people
- [ ] Kill-switch + shadow-mode env vars documented and tested

## 8. Governance
- [ ] Release-readiness checklist (this doc) filled in
- [ ] Launch decision memo drafted from template
- [ ] Retrospective placeholder created for T+30 post-launch
- [ ] Handoff checklist completed if a second operator will share on-call

---

## Sign-off

**Release version**: _____________________
**Release commit SHA**: _____________________
**Target launch window (UTC)**: _____________________
**Operator**: _____________________
**Date**: _____________________

I confirm all PASS/WAIVED items above. Any WAIVED item has a linked
compensating control. Any FAIL item blocks launch.

_Signature_: _____________________
