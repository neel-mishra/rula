---
title: "Pattern - Signed Claims Before Privileged Routing"
owner: "feature-owner-example-security"
date: "2026-04-20"
tags:
  - security
  - authz
  - rbac
  - provenance
component_domains:
  - security
  - governance
  - observability
risk_tier: "high"
related_files:
  - "rula-gtm-agent/src/security/rbac.py"
  - "rula-gtm-agent/src/landing_bridge.py"
  - "rula-gtm-agent/app.py"
related_prs:
  - "example-pr-002"
---

# Compound Retrospective

## Problem Pattern
- Trigger conditions:
  - privileged role resolved from untrusted or weakly trusted input.
- Failure mode or friction:
  - privilege escalation risk and poor forensic traceability.

## Solution Pattern
- What worked:
  - verify signed role claims before privileged route selection.
  - enforce deny/downgrade policy for invalid/tampered/expired claims.
  - emit structured auth decision telemetry.
- Why it worked:
  - access decisions became explicit, testable, and auditable.

## Prevention Rules
- Rule to prevent recurrence:
  - no privileged execution without signed, verified identity/role claim.
- Guardrail or checklist update:
  - quality gate requires auth decision-path test evidence for access-control changes.

## Validation Evidence
- Test or check evidence:
  - full claim matrix tests (valid/invalid/expired/tampered).
- Runtime/observability evidence:
  - deny/downgrade event telemetry captured with normalized reason codes.

## System Updates
- Template updates:
  - `04-templates/plan-template.md` emphasizes signed-claim validation for access changes.
- Checklist updates:
  - `05-checklists/quality-gate-checklist.md` requires security evidence for high-risk auth work.
- Rule/instruction updates:
  - security-critical entry boundaries require claim verification before role resolution.

