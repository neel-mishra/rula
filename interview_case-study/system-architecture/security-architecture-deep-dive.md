# Security, Safety, and Governance Architecture Deep Dive

This document maps the implemented security/safety/governance controls across the repository, with emphasis on runtime behavior in `rula-gtm-agent` and boundary behavior in `rula-landing-page`.

## Scope and system boundaries

| System area | Security/safety/governance role |
|---|---|
| `rula-gtm-agent` | Primary control plane: RBAC, sanitization, kill switches, circuit breakers, DLQ/incidents, retention, contract/version checks, telemetry policy, deterministic fallbacks, audit loops. |
| `business dna` | Governance data source (voice constraints, approved claims, context slices) consumed by pipelines; no auth or write surfaces. |
| `rula-landing-page` | UX launcher that builds deep links (`role`, `page`) to Streamlit app; explicitly demo-oriented role selection, not identity enforcement. |
| `interview_case-study`, `skills` | Documentation/process artifacts; no runtime enforcement layer. |

---

## Architecture summary (control flow)

The runtime flow in `rula-gtm-agent` follows this pattern:

1. **Entry + authorization check** via `require_permission` at orchestrator entrypoints.
2. **Safety gates**: kill-switch checks and circuit-breaker checks.
3. **Input sanitization** for account/evidence payloads.
4. **Pipeline execution** with deterministic and model-assisted stages.
5. **Audit/correction loop** before output acceptance.
6. **Failure handling** to DLQ + incident logs with redacted context.
7. **Append-only telemetry and lineage**, with metadata filtering.
8. **Governance operations** (retention pruning, contract/version checks, review queues, export caveats).

Source references:
- `docs/architecture_overview.md`
- `src/orchestrator/graph.py`

---

## Security architecture

### 1) Access control model (RBAC)

Implementation: `src/security/rbac.py`

- Roles: `admin`, `user`, `analyst`, `viewer` (+ internal `system`).
- Permissions are action-scoped (`prospecting:run`, `map:run`, `retention:run`, `incident:view`, `lineage:view`).
- `require_permission(role, permission)` is enforced in key privileged operations:
  - Prospecting run entry (`run_prospecting`)
  - MAP verification entry (`run_map_verification`)
  - Retention cleanup (`enforce_retention`)
- `resolve_role` behavior:
  - In `production`, effective role is hard-clamped to `viewer`.
  - In non-production, requested role is accepted if valid, else default `user`.

### 2) UI role behavior and trust boundary

Implementation: `app.py` and `rula-landing-page/components/LandingShell.tsx`

- Landing page allows selecting role and passes it via query params.
- Streamlit app applies query params in `_apply_landing_query_params`.
- In production, role selection is disabled and effective role stays `viewer`.
- Project docs explicitly state this is **not full authentication** and must be replaced with IdP-backed identity for real deployments.

Security implication:
- Current role control is an **application guardrail for prototype/demo contexts**, not a cryptographic/session-backed authn/authz boundary.

### 3) Input and persistence sanitization

Implementation: `src/safety/sanitize.py`

- `sanitize_account_payload`: bounds string fields and strips control characters.
- `sanitize_evidence_text`: strips controls and limits to max char budget.
- `sanitize_evidence_id`: normalizes identifiers and blocks unsafe path-like forms.
- `redact_context_for_persistence`:
  - Recursively redacts sensitive keys (`api_key`, `token`, `authorization`, `messages`, `prompt`, etc.).
  - Applies depth bound to avoid unbounded nested payload persistence.

This sanitizer is invoked in failure persistence paths (`src/safety/dlq.py`, `src/safety/incidents.py`), reducing secret leakage risk in local logs.

### 4) Filesystem and write safety

Implementations:
- `src/safety/paths.py`
- `src/safety/atomic_io.py`
- `src/integrations/map_handoff.py` (safe filename usage)

Controls:
- Path traversal protection via `assert_resolved_path_under_base`.
- Filename normalization + hash fallback via `safe_handoff_filename_component`.
- Atomic writes (`tempfile + os.replace`) for durable artifact output.
- Optional base-dir containment check on JSON writes.

---

## Safety architecture

### 1) Kill switches

Implementation: `src/safety/kill_switch.py`

- `RULA_DISABLE_PROSPECTING` and `RULA_DISABLE_MAP` can hard-disable each pipeline.
- Orchestrator checks kill switch before processing.

### 2) Circuit breakers

Implementation: `src/safety/circuit.py`, used in `src/orchestrator/graph.py`

- In-process breakers per pipeline (`prospecting_breaker`, `map_breaker`).
- Open after configurable consecutive failures; auto-recover after cooldown.
- Emits telemetry on open/closed transitions.

### 3) Failure containment: DLQ and incidents

Implementations:
- `src/safety/dlq.py`
- `src/safety/incidents.py`

Behavior:
- Exceptions are captured and written to `out/dlq.jsonl`.
- Incident record also created with severity (`high` for `PermissionError`/`RuntimeError`, otherwise `medium`).
- Context is redacted before writing.

### 4) Policy-based generation gating

Implementation: `src/agents/prospecting/dq_policy.py` + orchestrator usage

- YAML-configurable data-quality policy (`RULA_DQ_POLICY_PATH`).
- First matching rule wins.
- Actions:
  - `allow`
  - `soft_flag` (adds flags)
  - `block_generation` (skips generation and emits explicit skip output)

This gives safety/governance teams a declarative way to stop low-quality or risky input before content generation.

### 5) Audit and correction loops

Implementation: `src/orchestrator/graph.py`, `src/agents/audit/judge.py`

- Outputs go through a judge pass.
- If judge fails, bounded correction attempts (`MAX_AUDIT_RETRIES`) are applied.
- Results include audit pass/score metadata.

Note: judge is currently heuristic (not externally authenticated moderation service), but still functions as an internal quality/safety gate.

---

## Governance architecture

### 1) Data retention and lifecycle governance

Implementation: `src/governance/retention.py`

- Retention job prunes rows older than cutoff from:
  - `lineage.jsonl`
  - `telemetry_events.jsonl`
  - `out/feedback_memory.jsonl`
  - `out/dlq.jsonl`
  - `out/incidents.jsonl`
- Operation itself is RBAC-protected (`retention:run`).

### 2) Contract/version governance

Implementations:
- `src/integrations/contract_compat.py`
- `src/orchestrator/contracts.py`
- `src/orchestrator/map_contracts.py`

Controls:
- Enforced schema/contract version checks (`lineage`, `ingest`, `export`).
- Typed strict models (`extra="forbid"`) for subagent boundaries.
- Contract mismatch emits telemetry and raises explicit errors.

### 3) Export and handoff governance

Implementations:
- `src/integrations/export.py`
- `src/integrations/handoff.py`
- `src/integrations/map_handoff.py`
- docs: `docs/integration_contracts.md`

Controls:
- Exports include review/audit caveats and provenance fields.
- CRM handoff is modeled as simulated/read-only in v1 docs.
- Review queues are automatically populated for fails/review-needed items.
- Archive artifacts are written with atomic and path-safe helpers.
- Connector policy parameters (timeout/retry/idempotency scope) are centralized and emitted into telemetry metadata.

### 4) Telemetry governance and data minimization

Implementation: `src/telemetry/events.py`

- Telemetry metadata policy removes forbidden/sensitive keys at all nested depths.
- Depth and string-length caps prevent oversized or unsafe metadata payloads.
- Append-only JSONL event stream enables post-hoc auditability.

---

## LLM safety/governance integration

Primary related controls:

- **Provider reliability policy** (`src/integrations/connector_policy.py`) with connector-specific timeout/retry/idempotency defaults and env overrides.
- **Routing + fallback** (`src/providers/router.py`) with provider fallback and generation telemetry.
- **Prompt/output constraints** in generation and validation paths:
  - Structured output constraints
  - Validation checks
  - Repair attempts
  - Deterministic template fallback on failure

Even when models fail, system behavior remains bounded due to deterministic fallback and audit controls.

---

## Landing page security posture (`rula-landing-page`)

This app is a launcher/orchestration UI, not an enforcement boundary.

- Builds Streamlit deep links with `role` and `page` query parameters (`lib/streamlit-url.ts`).
- Stores role in localStorage for UX continuity.
- Explicit UI copy notes production lock behavior and references backend enforcement model.
- No dedicated auth middleware, session management, or policy engine in this subproject.

Governance implication: trust boundary sits in the Streamlit/backend layer, not the launcher.

---

## Implemented controls matrix

| Control category | Implemented? | Where |
|---|---|---|
| Role-based authorization checks | Yes | `src/security/rbac.py`, `src/orchestrator/graph.py`, `src/governance/retention.py` |
| Production role clamp | Yes | `resolve_role` + `app.py` |
| Kill switches | Yes | `src/safety/kill_switch.py` |
| Circuit breakers | Yes | `src/safety/circuit.py` |
| Input sanitization | Yes | `src/safety/sanitize.py` |
| Secret redaction in failure logs | Yes | `src/safety/sanitize.py`, `dlq.py`, `incidents.py` |
| Atomic writes | Yes | `src/safety/atomic_io.py` |
| Path traversal protection | Yes | `src/safety/paths.py` |
| Data retention pruning | Yes | `src/governance/retention.py` |
| Contract/schema version enforcement | Yes | `src/integrations/contract_compat.py` |
| Telemetry metadata filtering | Yes | `src/telemetry/events.py` |
| DQ policy gate (skip/soft-flag/block) | Yes | `src/agents/prospecting/dq_policy.py` |
| Human review queue routing | Yes | `src/integrations/handoff.py`, `map_handoff.py` |
| Full IdP-backed authentication | No (documented gap) | README + architecture docs |
| Live CRM write with promotion gates | Not enabled in v1 | `docs/integration_contracts.md` |

---

## Risks and gaps (current-state assessment)

1. **Authentication is demo-grade, not enterprise-grade**
   - Role can be selected client-side outside production contexts.
   - Production viewer lock is protective but does not replace identity assertions.

2. **Authorization enforcement depends on call-path discipline**
   - Core orchestrators enforce permissions, but any future bypass path must also enforce `require_permission`.
   - This is manageable with coding standards/tests but not impossible to regress.

3. **Local JSONL persistence model**
   - DLQ/incidents/telemetry/lineage are file-backed; suitable for prototype but not hardened centralized logging/audit infra.
   - OS-level file permissions/encryption-at-rest are external to app code.

4. **Circuit breaker currently “future LLM/provider” oriented**
   - Breakers exist and are wired at pipeline level, but not all connector calls are individually guarded by connector-scoped breaker logic.

5. **No network perimeter controls in repo**
   - TLS termination, WAF, IP policies, and secret manager integration are deployment concerns not codified here.

---

## Recommended next hardening steps

1. Integrate real authn/authz (OIDC/SAML/JWT) and map claims to RBAC server-side.
2. Add signed/auditable actor identity propagation into all telemetry/audit records.
3. Move JSONL artifacts to managed logging/event storage with retention + immutability policies.
4. Add policy-as-code checks in CI to ensure all new entrypoints call `require_permission`.
5. Add secret scanning and prompt/PII leak tests on DLQ/telemetry payload paths.
6. Formalize incident severity taxonomy and escalation workflows beyond local JSONL records.

---

## File reference index

- Security
  - `src/security/rbac.py`
  - `app.py`
- Safety
  - `src/safety/sanitize.py`
  - `src/safety/kill_switch.py`
  - `src/safety/circuit.py`
  - `src/safety/dlq.py`
  - `src/safety/incidents.py`
  - `src/safety/paths.py`
  - `src/safety/atomic_io.py`
- Governance
  - `src/governance/retention.py`
  - `src/integrations/contract_compat.py`
  - `src/integrations/export.py`
  - `src/integrations/handoff.py`
  - `src/integrations/map_handoff.py`
  - `src/agents/prospecting/dq_policy.py`
  - `src/telemetry/events.py`
- Docs
  - `docs/architecture_overview.md`
  - `docs/integration_contracts.md`
  - `docs/ingest_contract.md`
  - `README.md`

