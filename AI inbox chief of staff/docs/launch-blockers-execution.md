# Launch-blocker execution guide (P1)

This document turns items from [quality-gates.md](quality-gates.md), [release-readiness.md](release-readiness.md), and [risk-register.md](risk-register.md) into **actionable operator steps**. Run in parallel with MVP deployment where noted.

---

## 1. Google OAuth consent (Risk R1, Gate 1.a / 1.d)

**Goal:** Approved OAuth consent (or limited test users) for Gmail-sensitive scopes.

**Actions:**

1. Confirm OAuth client is in correct GCP project; scopes match [`core/gmail/auth.py`](../core/gmail/auth.py) (no `gmail.send`).
2. Add production/ staging API callback to **Authorized redirect URIs**:  
   `https://<render-api>/mailbox-connect/gmail/callback`
3. Complete consent screen: app name, support email, privacy policy URL, terms (if required).
4. For pre-verification: add **test users** in OAuth consent screen.
5. Submit for verification when moving beyond internal testers (plan 4–6 weeks).

**Evidence to capture:** screenshot of OAuth consent status; list of test users; confirmation redirect URI in Console.

---

## 2. Gold-eval dataset (Risk R3, Gate 2.d, 7.b)

**Goal:** Representative labeled set to prove triage/draft quality beyond synthetic tests.

**Actions:**

1. Enable sampling only in controlled env (see `GOLD_SAMPLING_ENABLED`, `GOLD_EVAL_ENABLED` in `core/config.py`).
2. Curate minimum target (e.g. 100+ cases) per [quality-gates.md](quality-gates.md) Gate 2.d.
3. Run evaluator pipeline; store metrics snapshot.

**Evidence:** export path or dashboard screenshot; pass/fail vs SLO targets in [release-readiness.md](release-readiness.md).

---

## 3. Backup / restore drill (Risk R8, Gate 6.c, 7 launch rule)

**Goal:** Verified RTO/RPO; no launch without evidence per project policy (unless formally waived).

**Actions:**

1. Follow [backup-restore-drill.md](backup-restore-drill.md) (or equivalent Runbook).
2. Run dry-run in staging; then `RUN=1` (or prod read-only rehearsal if approved).
3. Record row-count parity and restoration time.

**Evidence:** drill log artifacts; operator sign-off date.

---

## 4. Alerting dry-run (Gate 6.d partial)

**Goal:** Severity-1 path reaches Slack/PagerDuty and is acknowledged.

**Actions:**

1. Configure `SLACK_WEBHOOK_URL` / `PAGERDUTY_ROUTING_KEY` in Render (or secret store).
2. Trigger test alert from [`core/alerts/`](../core/alerts/) path or documented manual trigger.
3. Confirm on-call acknowledges.

**Evidence:** timestamp + ack screenshot.

---

## 5. Release readiness sign-off

**Goal:** Single accountable sign-off before production traffic.

**Actions:**

1. Fill [release-readiness.md](release-readiness.md) checklist (PASS / FAIL / WAIVED).
2. Attach pointers to sections 1–4 evidence above.

---

## Status template (copy to PR or ops ticket)

| Blocker | Owner | Status | Evidence link |
|---------|-------|--------|-----------------|
| OAuth R1 | | OPEN / DONE | |
| Gold-eval R3 | | OPEN / DONE | |
| Backup drill R8 | | OPEN / DONE | |
| Alerts 6.d | | OPEN / DONE | |
| Release memo | | OPEN / DONE | |
