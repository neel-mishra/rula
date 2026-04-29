# External Best Practices (Adapted)

## Sources

- OWASP ASVS: https://asvs.dev/
- Google SRE monitoring and golden signals: https://sre.google/sre-book/monitoring-distributed-systems/
- Google SRE error budget policy example: https://sre.google/workbook/error-budget-policy/
- Feature toggles and progressive release practice: https://martinfowler.com/articles/feature-toggles.html

## Best-Practice Domains

## 1) Security Engineering

Adopt:
- verification-standard mindset (ASVS-style controls)
- security checks across requirements/design/implementation/verification
- explicit secure coding and validation checkpoints

Apply here:
- map hard blockers and risk tiers to security controls
- ensure high-risk merges cannot bypass security maturity thresholds

## 2) Reliability and Operations

Adopt:
- golden signals: latency, traffic, errors, saturation
- actionable alerting with low noise and high signal
- SLO-driven error budget policy to balance speed and reliability

Apply here:
- define SLO/SLI expectations per critical workflow
- codify release pause/rollback triggers when reliability budgets are exceeded

## 3) Data Integrity and Contracts

Adopt:
- contract-first schema governance
- explicit change policy for backward compatibility
- quality checks at ingestion and before output

Apply here:
- treat schema changes like API changes
- force compatibility evidence for high-risk data-path merges

## 4) Release Safety and Progressive Delivery

Adopt:
- separate deployment from release using feature flags
- use canary or phased rollouts for risk-heavy changes
- actively manage feature-flag lifecycle to avoid toggle debt

Apply here:
- require rollout plans in release-readiness docs
- mandate cleanup ownership for transient feature flags

## 5) Process Compounding

Adopt:
- structured post-change learning
- metadata-rich knowledge artifacts
- recurring operational retrospectives that update standards

Apply here:
- weekly compounding ritual
- mandatory compound artifact for high-risk changes
- continuous updates to templates, checklists, and rules

## End-to-End Build Checklist (External + Repo-Aligned)

1. Define outcome, constraints, and risk tier.
2. Map affected components and contracts.
3. Define security and integrity guardrails.
4. Define observability and reliability signals.
5. Implement with deterministic-first and controlled probabilistic behavior.
6. Validate with tests and risk-aligned review.
7. Roll out progressively with rollback triggers.
8. Capture reusable learning and update the system.

