---
title: "Add Contract Compatibility Gate for Export Payloads"
owner: "feature-owner-example"
status: "approved"
risk_tier: "high"
date: "2026-04-20"
---

# Plan

## Problem and Outcome
- Problem: export payload changes can silently break downstream consumers.
- User/business outcome: enforce compatibility checks before export release to reduce integration breakages.
- Non-goals: replacing the existing export format or introducing a new schema registry service in this iteration.

## Context and Constraints
- Existing patterns to follow: contract-first schemas and compatibility checks already exist in `rula-gtm-agent/src/integrations/contract_compat.py`.
- Constraints:
  - must preserve current shadow-mode handoff behavior
  - must maintain deterministic fallback for malformed generation artifacts
- Dependencies:
  - `rula-gtm-agent/src/integrations/export.py`
  - `rula-gtm-agent/src/schemas/*`

## Scope
- In scope:
  - add strict pre-export compatibility validation
  - add test coverage for breaking/non-breaking contract scenarios
  - add telemetry event on compatibility failure
- Out of scope:
  - live downstream adapter integration
  - external schema registry integration

## Architecture and Components Affected
- Components:
  - data integrity/contracts
  - output/handoff integration boundary
  - observability
- Data contracts/schemas:
  - export payload compatibility and version fields
- Security implications:
  - no new auth surface introduced
- Observability implications:
  - add explicit compatibility failure event and metric increment

## Implementation Steps
1. Add compatibility gate call before export handoff write.
2. Emit structured telemetry on gate pass/fail.
3. Add tests for backward-compatible and breaking changes.
4. Update release-readiness artifact with compatibility evidence.

## Validation Strategy
- Tests: unit tests for compatibility validator and export integration tests.
- Lint/type checks: run project lint and type validations.
- Manual verification: run sample export from UI and inspect generated payloads.
- Runtime validation: confirm telemetry events include contract status.

## Rollout and Rollback
- Rollout plan:
  - enable gate in shadow mode first
  - review one week of compatibility telemetry
  - promote to strict block mode for high-risk releases
- Rollback trigger:
  - false-positive rate above threshold or high-volume blocked exports without actual contract break
- Rollback steps:
  - switch gate to warning mode
  - preserve telemetry collection
  - patch validator rules

## Risks and Mitigations
- Risk: false positives block safe exports
  - Mitigation: warning-only warm-up and rule tuning window
- Risk: telemetry noise
  - Mitigation: standardized event schema and dedupe key

## Approval
- Approved by: feature-owner-example
- Approval timestamp: 2026-04-20T18:00:00Z

