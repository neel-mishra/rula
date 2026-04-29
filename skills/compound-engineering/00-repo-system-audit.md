# Repo System Audit

## Scope

This audit covers the current repository as a reference system:
- `rula-gtm-agent` (primary runtime and orchestration core)
- `rula-landing-page` (entry UX and deep-link bridge)
- `business dna` (domain context corpus)
- `interview_case-study` (system strategy and architecture artifacts)

## Architecture Snapshot

- Primary execution runs in `rula-gtm-agent/app.py` with role-aware UI and workflow routing.
- Pipeline orchestration is centered in `rula-gtm-agent/src/orchestrator/graph.py` with bulk runners in `src/orchestrator/bulk_prospecting.py` and `src/orchestrator/bulk_map.py`.
- Domain agents are split into:
  - Prospecting (`src/agents/prospecting/*`)
  - MAP verification (`src/agents/verification/*`)
  - Audit/correction (`src/agents/audit/*`)
- LLM interactions are abstracted via `src/providers/*` with routing/fallback behavior.
- Integration contracts and handoffs are managed in `src/integrations/*`.
- Cross-cutting controls are explicit: `src/security/*`, `src/safety/*`, `src/governance/*`, `src/telemetry/*`.

## End-to-End Flow

1. Landing app builds deep link (`rula-landing-page/lib/streamlit-url.ts`).
2. Streamlit app resolves role and page context (`app.py`, `src/landing_bridge.py`, `src/security/rbac.py`).
3. Orchestrator runs prospecting or MAP pipelines with guardrails.
4. Outputs are validated, audited, and packaged.
5. Export/handoff writes contract-shaped artifacts and telemetry.
6. Insights and governance layers consume events/metrics and enforce retention.

## Component Breakout (Current State)

### Security
- Present: RBAC checks, role clamping, sanitization/redaction, path safety.
- Gaps: no production-grade authn integration or signed identity boundary.

### Data Integrity and Contracts
- Present: typed schemas, contract compatibility checks, strict pipeline boundaries.
- Gaps: no external schema registry or automated compatibility CI gate.

### Data Ingestion
- Present: fixture-based ingestion and documented ingest contracts.
- Gaps: no production ingestion endpoint or queue-backed ingestion service.

### Execution and Orchestration
- Present: deterministic-first orchestrators, bulk runners, subagent wiring.
- Gaps: no distributed worker runtime or durable workflow state store.

### Decision Layer (Deterministic + LLM)
- Present: prompt abstractions, provider routing, fallback and validation.
- Gaps: no cost governance policy or centralized prompt registry lifecycle.

### Output and Integrations
- Present: export contracts and local handoff archive paths.
- Gaps: no live outbound adapters with transactional guarantees.

### Reliability and Safety
- Present: kill switches, circuit breaker, DLQ/incident recording, atomic writes.
- Gaps: no externalized incident automation and runbook-driven remediation loops.

### Observability and Lineage
- Present: JSONL events, metrics aggregation, lifecycle/UX telemetry.
- Gaps: no centralized log/metric backend, SLO alerting, or distributed tracing.

### Governance and Retention
- Present: retention pruning, context provenance, policy-aware generation controls.
- Gaps: no policy-as-code enforcement and limited formal approval workflows.

### UX and System Boundaries
- Present: role-based guided flows and cross-app deep-link contract.
- Gaps: coupling to local runtime process; no durable user session/back-end API boundary.

## Strengths

- Clear modular boundaries across agents, providers, integrations, and controls.
- Strong deterministic-first pattern with bounded LLM surface area.
- Contract-first thinking with schema validation and compatibility checks.
- Safety posture is implemented in code, not only documented.
- Extensive documentation and readiness artifacts already exist.

## Critical Gaps

- CI/CD automation and branch/PR governance are under-specified.
- Production-grade identity and access boundary is incomplete.
- Operational observability and reliability policy are not fully externalized.
- Integration adapters are largely modeled/simulated, not production-connected.

## Compound Engineering Implications

- Keep existing architecture style: deterministic core + controlled probabilistic edges + explicit control plane.
- Prioritize process/system upgrades (gates, standards, automations) that reduce repeated manual review.
- Use this audit as the baseline evidence source for maturity scoring in `11-system-component-breakout.md`.

