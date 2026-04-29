# Operating Model

## Roles

- Feature Owner (single accountable owner): owns plan, execution, review closure, and compound artifact.
- Reviewer(s): validate intent, business logic, UX impact, and risk posture.
- Domain Approvers (as needed): security/data/governance sign-off for domain-specific concerns.

## Work Modes

### Single-feature mode

Use for low-coupling or moderate-risk changes.
1. Produce approved plan.
2. Execute in isolated branch/workstream.
3. Run validations and reviews.
4. Resolve findings.
5. Produce compound artifact.

### Multi-feature mode

Use for high throughput with bounded coupling.
1. Split into independent slices with explicit boundaries.
2. Parallelize research and implementation where safe.
3. Centralize integration risk checks.
4. Merge in controlled sequence with rollout guards.

## Risk Tiers

- Low risk: localized behavior, no contract/security impact.
- Medium risk: cross-module behavior with bounded blast radius.
- High risk: security, contracts, core flow UX, reliability critical paths.

## Merge Gates by Risk Tier

- Low: checklist + targeted tests + review evidence.
- Medium: low-tier gates + integration validation + risk note.
- High: strict gate:
  - tests + lint + type checks
  - risk register entry
  - explicit rollback plan
  - maturity thresholds met for critical domains (see `11-system-component-breakout.md`)

## Review Policy

- P1 must fix before merge.
- P2 should fix before merge unless explicitly deferred with owner and due date.
- P3 optional; may be queued for compounding backlog.

## Weekly Compounding Ritual

Cadence: weekly.

Agenda:
1. Review merged work and incidents/findings.
2. Extract reusable patterns and anti-patterns.
3. Update templates/checklists/rules.
4. Re-score domain maturity and log deltas.
5. Assign system-improvement actions for next cycle.

