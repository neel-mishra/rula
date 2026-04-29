---
title: "Add Signed Role Claims and Server-Side Auth Gate"
owner: "feature-owner-example-security"
status: "approved"
risk_tier: "high"
date: "2026-04-20"
---

# Plan

## Problem and Outcome
- Problem: role selection in the current flow is suitable for demo/prototype use but does not enforce production-grade identity claims.
- User/business outcome: enforce authenticated, signed role claims so privileged workflows cannot be accessed by unsigned role input.
- Non-goals: full enterprise SSO rollout in this iteration.

## Context and Constraints
- Existing patterns to follow:
  - RBAC checks in `rula-gtm-agent/src/security/rbac.py`
  - role-aware runtime flow in `rula-gtm-agent/app.py`
- Constraints:
  - preserve current local-dev ergonomics
  - avoid breaking existing viewer workflows
  - maintain explicit auditability for access decisions
- Dependencies:
  - `rula-gtm-agent/src/security/rbac.py`
  - `rula-gtm-agent/src/landing_bridge.py`
  - `rula-gtm-agent/app.py`

## Scope
- In scope:
  - introduce signed role-claim verification at entry boundary
  - reject or downgrade unsigned/invalid privileged claims
  - emit telemetry/audit events on auth decision paths
  - add tests for valid, invalid, expired, and tampered claims
- Out of scope:
  - enterprise identity provider integration
  - multi-tenant org hierarchy model

## Architecture and Components Affected
- Components:
  - security and access control
  - execution boundary protection
  - governance/provenance
  - observability
- Data contracts/schemas:
  - signed claim payload fields and validation rules
- Security implications:
  - privileged execution now requires verified claim input
- Observability implications:
  - capture access-allow, access-deny, and downgrade events

## Implementation Steps
1. Add signed claim verifier utility and canonical claim schema.
2. Wire claim verification into entry bridge before role resolution.
3. Enforce deny/downgrade policy for invalid privileged claims.
4. Emit audit telemetry for each auth decision path.
5. Add full test matrix for claim handling and RBAC outcomes.

## Validation Strategy
- Tests:
  - claim parsing/verification unit tests
  - RBAC integration tests for permission outcomes
  - negative tests for tampered and expired claims
- Lint/type checks:
  - run repository lint/type validations
- Manual verification:
  - simulate privileged and non-privileged launch flows
- Runtime validation:
  - verify auth decision telemetry is complete and sanitized

## Rollout and Rollback
- Rollout plan:
  - phase 1: warning mode with telemetry-only deny simulation
  - phase 2: hard-enforcement for privileged roles
  - phase 3: remove warning mode after stability window
- Rollback trigger:
  - valid users blocked due to verifier regressions
- Rollback steps:
  - revert to warning mode
  - preserve denial telemetry
  - hotfix verifier logic and re-run validation matrix

## Risks and Mitigations
- Risk: false denial for valid users
  - Mitigation: warning-mode warmup + strict test matrix
- Risk: claim replay or tampering edge cases
  - Mitigation: signature verification + timestamp/expiry checks
- Risk: insufficient observability for auth failures
  - Mitigation: mandatory audit event fields + failure reason taxonomy

## Approval
- Approved by: feature-owner-example-security
- Approval timestamp: 2026-04-20T18:30:00Z

