---
title: "Pattern - Contract Gate Before Export"
owner: "feature-owner-example"
date: "2026-04-20"
tags:
  - contracts
  - data-integrity
  - export
component_domains:
  - data-integrity
  - output-handoff
  - observability
risk_tier: "high"
related_files:
  - "rula-gtm-agent/src/integrations/export.py"
  - "rula-gtm-agent/src/integrations/contract_compat.py"
related_prs:
  - "example-pr-001"
---

# Compound Retrospective

## Problem Pattern
- Trigger conditions:
  - export payload updated while downstream expects prior contract version.
- Failure mode or friction:
  - silent downstream processing errors and delayed detection.

## Solution Pattern
- What worked:
  - enforce compatibility gate before payload handoff.
  - emit explicit pass/fail telemetry with version pair metadata.
- Why it worked:
  - failures became immediate and actionable instead of latent.

## Prevention Rules
- Rule to prevent recurrence:
  - any high-risk export change must include compatibility test evidence.
- Guardrail or checklist update:
  - `05-checklists/quality-gate-checklist.md` requires contract compatibility validation.

## Validation Evidence
- Test or check evidence:
  - compatibility tests for breaking and non-breaking cases.
- Runtime/observability evidence:
  - telemetry showed expected pass/fail events in shadow rollout.

## System Updates
- Template updates:
  - `04-templates/release-readiness-template.md` now expects compatibility gate evidence.
- Checklist updates:
  - quality gate checklist includes explicit contract validation line.
- Rule/instruction updates:
  - high-risk merge requires compatibility evidence for changed contract surfaces.

