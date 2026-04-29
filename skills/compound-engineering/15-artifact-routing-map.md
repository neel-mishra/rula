# Artifact Routing Map

## IntentKeywords

- implementation: build, implement, add, change, refactor, fix, create script, wire, integrate, ship
- readonly: review, explain, summarize, analyze, audit, compare

## DomainMappings

- security: security, auth, authentication, authorization, rbac, permission, access, token, claim, secret
- data-integrity: schema, contract, compatibility, validation, integrity, version, migration
- ingestion: ingest, ingestion, import, parse input, source data, normalize
- output-handoff: export, output, handoff, delivery, downstream, connector, payload
- reliability: reliability, outage, rollback, failover, error budget, slo, sli, incident
- observability: telemetry, metrics, logs, tracing, dashboard, alert, monitoring
- release-management: release, rollout, canary, feature flag, deploy, go-live
- governance: retention, provenance, compliance, audit trail, policy, triage

## RequiredArtifactsByDomain

- security:
  - skills/compound-engineering/11-system-component-breakout.md
  - skills/compound-engineering/05-checklists/quality-gate-checklist.md
  - skills/compound-engineering/09-governance-and-triage.md
- data-integrity:
  - skills/compound-engineering/11-system-component-breakout.md
  - skills/compound-engineering/04-templates/plan-template.md
  - skills/compound-engineering/04-templates/release-readiness-template.md
- ingestion:
  - skills/compound-engineering/11-system-component-breakout.md
  - skills/compound-engineering/00-repo-system-audit.md
  - skills/compound-engineering/04-templates/plan-template.md
- output-handoff:
  - skills/compound-engineering/11-system-component-breakout.md
  - skills/compound-engineering/04-templates/release-readiness-template.md
  - skills/compound-engineering/05-checklists/quality-gate-checklist.md
- reliability:
  - skills/compound-engineering/12-external-best-practices.md
  - skills/compound-engineering/07-metrics-and-compounding.md
  - skills/compound-engineering/08-roadmap.md
- observability:
  - skills/compound-engineering/12-external-best-practices.md
  - skills/compound-engineering/07-metrics-and-compounding.md
  - skills/compound-engineering/11-system-component-breakout.md
- release-management:
  - skills/compound-engineering/05-checklists/quality-gate-checklist.md
  - skills/compound-engineering/04-templates/release-readiness-template.md
  - skills/compound-engineering/08-roadmap.md
- governance:
  - skills/compound-engineering/09-governance-and-triage.md
  - skills/compound-engineering/10-compound-memory-spec.md
  - skills/compound-engineering/05-checklists/handoff-checklist.md

## RecommendedArtifactsByDomain

- security:
  - skills/compound-engineering/13-example-feature-packet-security/01-plan-example.md
  - skills/compound-engineering/13-example-feature-packet-security/02-review-example.md
  - skills/compound-engineering/13-example-feature-packet-security/03-compound-example.md
- data-integrity:
  - skills/compound-engineering/13-example-feature-packet/01-plan-example.md
  - skills/compound-engineering/13-example-feature-packet/02-review-example.md
  - skills/compound-engineering/13-example-feature-packet/03-compound-example.md
- ingestion:
  - skills/compound-engineering/00-repo-system-audit.md
  - skills/compound-engineering/03-operating-model.md
- output-handoff:
  - skills/compound-engineering/00-repo-system-audit.md
  - skills/compound-engineering/03-operating-model.md
- reliability:
  - skills/compound-engineering/12-external-best-practices.md
  - skills/compound-engineering/14-weekly-rollout-checklist.md
- observability:
  - skills/compound-engineering/12-external-best-practices.md
  - skills/compound-engineering/14-weekly-rollout-checklist.md
- release-management:
  - skills/compound-engineering/14-weekly-rollout-checklist.md
  - skills/compound-engineering/03-operating-model.md
- governance:
  - skills/compound-engineering/10-compound-memory-spec.md
  - skills/compound-engineering/14-weekly-rollout-checklist.md

## FallbackRules

- If no domain keywords match:
  - require explicit domain tag in task text in the form `domain:<name>`, or
  - require fallback rationale text in the form `fallback:<reason>`
- If multiple domains match:
  - highest-risk domain is primary using precedence:
    1. security
    2. data-integrity
    3. governance
    4. reliability
    5. release-management
    6. observability
    7. ingestion
    8. output-handoff

## BypassPolicy

- Bypass is allowed only when all fields are provided:
  - `CE_BYPASS_REASON`
  - `CE_BYPASS_OWNER`
  - `CE_BYPASS_FOLLOWUP`
- Bypass must produce a follow-up governance item in the same cycle.

