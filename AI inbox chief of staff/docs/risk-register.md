# Risk Register

**Status**: v1
**Cadence**: Review weekly until launch; monthly post-launch or on sev1+ incident.
**Owner**: Neel (operator).
**Companions**: `threat-model.md`, `data-classification.md`, `incident-operations.md`.

Each row captures a delivery or operational risk with likelihood (1–5),
impact (1–5), current mitigation (what's already in code or process), residual
risk (what's still open), and the review date on which the status was last
updated.

Score = Likelihood × Impact. Items with score ≥ 15 must have an explicit
mitigation plan before Gate 7; items ≥ 20 are launch blockers until closed.

---

## Delivery Risks

### R1. Google Cloud OAuth consent screen not approved in time
- **Likelihood**: 3  **Impact**: 5  **Score**: 15
- **Blast radius**: No real mailbox testing → no Gate 1 sign-off → launch slips.
- **Mitigation**: Auth flow + scope decisions already coded; consent screen
  copy drafted in the privacy notice; limited-audience mode unblocks internal
  testing before full verification.
- **Residual**: Google app-verification review time is out of our control
  (typically 4–6 weeks for sensitive scopes).
- **Owner**: Neel
- **Status**: OPEN
- **Last review**: 2026-04-24

### R2. Production AWS infrastructure not provisioned
- **Likelihood**: 2  **Impact**: 5  **Score**: 10
- **Blast radius**: No staging → no backup/restore drill (H.19) → Gate 7 blocker.
- **Mitigation**: Terraform under `infra/` is written and validated; CI/CD
  pipeline deploys to ECR on merge; remaining work is `terraform apply` + IAM
  + KMS + Secrets Manager bootstrap.
- **Residual**: One-shot provisioning error could delay launch by days.
- **Owner**: Neel
- **Status**: OPEN
- **Last review**: 2026-04-24

### R3. Real gold-eval dataset gap
- **Likelihood**: 4  **Impact**: 4  **Score**: 16
- **Blast radius**: Gate 2/3 quality targets (false-archive, draft grounding)
  cannot be proven on representative data — launch numbers are synthetic.
- **Mitigation**: Nightly eval pipeline + A/B framework already run against
  live data; metrics instrumentation captures real-traffic outcomes
  (`core/slo/metrics.py`).
- **Residual**: Adversarial / long-tail cases (forwarded receipts, multi-lingual
  threads, calendar invites) under-represented.
- **Owner**: Neel
- **Status**: OPEN — curate 100+ golden cases before Gate 2 sign-off.
- **Last review**: 2026-04-24

---

## Security Risks

### R4. Prompt injection escaping the hard-block + soft-strip layers
- **Likelihood**: 3  **Impact**: 5  **Score**: 15
- **Blast radius**: Model takes an attacker-controlled action (archive, label,
  draft). Undo ledger reverses it but reputational damage still lands.
- **Mitigation**: 17 adversarial tests passing at 100%; attachment extractor
  bounds text size; safety-first fallback to `INBOX_KEEP` on detection;
  no `gmail.send` scope means the worst case is misclassification, not send.
- **Residual**: Unicode homoglyph / zero-width / PDF-embedded payloads not
  yet in the adversarial suite (see `threat-model.md` §2 follow-ups).
- **Owner**: Neel
- **Status**: OPEN — schedule adversarial-PDF fixtures before auto-mode rollout.
- **Last review**: 2026-04-24

### R5. OAuth refresh-token theft from DB
- **Likelihood**: 2  **Impact**: 5  **Score**: 10
- **Blast radius**: Attacker gains read/label/draft access to a user's Gmail.
- **Mitigation**: Fernet/KMS envelope encryption at rest; plaintext never
  persisted; revocation on disconnect; proactive refresh with jitter.
- **Residual**: Key rotation runbook not yet written;
  `APP_SECRET_KEY`/KMS-key compromise is the single point of failure.
- **Owner**: Neel
- **Status**: OPEN — add rotation runbook + break-glass procedure.
- **Last review**: 2026-04-24

### R6. Supply-chain compromise via new optional deps (pypdf, python-docx)
- **Likelihood**: 2  **Impact**: 3  **Score**: 6
- **Blast radius**: Malicious update parses attacker-crafted attachment and
  executes in the ingest worker.
- **Mitigation**: Both libs are import-guarded — absent libs degrade gracefully
  to `extractor=None`; worker runs in an isolated container; attachment bytes
  are bounded at 20 MiB.
- **Residual**: No SBOM scanning in CI yet; versions not pinned.
- **Owner**: Neel
- **Status**: OPEN — pin versions in `pyproject.toml`, add `pip-audit` to CI.
- **Last review**: 2026-04-24

---

## Reliability / Operations Risks

### R7. LLM provider circuit-breaker trip cascades across both providers
- **Likelihood**: 3  **Impact**: 4  **Score**: 12
- **Blast radius**: All triage falls back to deterministic inbox-keep; drafts
  + briefs stop generating for the cooldown period (120s + error recovery).
- **Mitigation**: Per-provider breaker isolates Anthropic from OpenAI; 5-failure
  trip threshold over 60s window; alert to Slack/PagerDuty on trip; kill
  switch bypasses LLM entirely without crashing.
- **Residual**: No multi-region fallback; both providers sharing a single
  upstream networking issue would trip both.
- **Owner**: Neel
- **Status**: OPEN — acceptable until a third provider (Gemini, I.8) is wired.
- **Last review**: 2026-04-24

### R8. Backup/restore drill not yet executed
- **Likelihood**: 3  **Impact**: 5  **Score**: 15
- **Blast radius**: RTO/RPO targets (60min / 5min) are unverified; a real
  DB incident could cause permanent data loss.
- **Mitigation**: RDS automated backups enabled by default in terraform;
  immutable audit log provides append-only recovery reference.
- **Residual**: No dry-run of the restore path; cross-region snapshot copy
  policy not defined; key rotation during restore untested.
- **Owner**: Neel
- **Status**: OPEN — Gate 7 blocker.
- **Last review**: 2026-04-24

### R9. Per-mailbox token budget exhaustion masks real quality regressions
- **Likelihood**: 3  **Impact**: 2  **Score**: 6
- **Blast radius**: Mailbox silently drops to deterministic mode for the rest
  of the day; triage accuracy degrades.
- **Mitigation**: Daily + monthly budgets with auto-degradation at 80%;
  structured log events (`budget.daily_exhausted`); SLO dashboard surfaces
  downstream effect (correction rate spike).
- **Residual**: No user-facing notification when budget is hit; they find out
  by spotting drift.
- **Owner**: Neel
- **Status**: OPEN — add in-app banner when auto-degradation fires.
- **Last review**: 2026-04-24

---

## Product / UX Risks

### R10. Hidden false-archive cases masked by user habit
- **Likelihood**: 4  **Impact**: 3  **Score**: 12
- **Blast radius**: Users accept bad archives silently → false-archive SLO
  reads green → trust erodes once a visible miss lands.
- **Mitigation**: 7-day undo window with one-click UI; email notification on
  every archive (content TBD); weekly correction-conversion metric (G.11
  follow-up) will surface drift even without explicit user feedback.
- **Residual**: Correction-conversion worker not yet wired; onboarding does
  not explain the undo UX yet.
- **Owner**: Neel
- **Status**: OPEN — ship onboarding tour + weekly rollup before launch.
- **Last review**: 2026-04-24

---

## Scoring Scale

**Likelihood**
1. Remote — no known trigger
2. Unlikely — single known trigger, requires extra steps
3. Possible — occurs under normal stress
4. Likely — expected within the first month of real use
5. Near-certain — expected within the first week

**Impact**
1. Cosmetic — negligible effect
2. Minor — recovers within a business day
3. Moderate — a user-visible degradation that persists for hours
4. Major — user data integrity or silent wrong action; requires post-mortem
5. Severe — launch blocker / compliance violation / data loss

---

## Change Log

- **2026-04-24 (v1)**: Initial 10-risk register covering delivery, security,
  reliability, and product buckets. Six items OPEN with score ≥ 10; no score
  ≥ 20 (no absolute launch blockers from the register alone).
