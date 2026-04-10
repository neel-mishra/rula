# Findings by Pillar

**Review execution date:** 2026-04-11.  
**Codebase:** `rula-gtm-agent/` — Streamlit UI, Prospecting/MAP orchestrators, integrations, hardened connector surfaces (policy registry, contract compatibility, atomic IO, lifecycle IDs/events).

---

## Pillar 1 — Contextual integrity and state

- **Pydantic v2** models live under `src/schemas/`; orchestrator contracts in `contracts.py` / `map_contracts.py` support execution agents. **Evidence:** `LineageExportBlock` and `CommitmentEvidenceArtifact` enforce `schema_version` via validators tied to `contract_compat.py`.
- **Lifecycle IDs** (`correlation_id`, `prospecting_run_id`, `map_run_id`, optional CRM-thread fields) are attached in `graph.py`, propagated to exports and MAP/prospecting CRM manifest rows; **shadow** compare strips per-run lifecycle keys for fair structural diff (`shadow.py`).
- **Streamlit `st.session_state`** (`app.py`): bulk summaries, single-run results, navigation (`_ui_nav_page`), email edit keys, **MAP bridge** (`map_bridge_*`) for Promote-to-MAP — intentional but complex; reruns can interleave; acceptable for prototype if documented.
- **Config** (`config.py`): env-driven; DQ, lineage, bulk queue, connector policy overrides (`RULA_CONNECTOR_*` per `docs/connector_policies.md`). Business DNA fails closed via registry when missing.
- **Imports:** Test suite (316 tests) exercises primary import graph; no systematic unresolved-import failures observed.

---

## Pillar 2 — Logic and edge cases

- **Bulk prospecting/map:** `bulk_prospecting.py`, `bulk_map.py` — pass/review/error/skip semantics; queue mode on summary; tests cover DQ, queue order, bulk MAP.
- **DQ + graph:** Early exit for policy skips; lifecycle domain events emitted for assigned/outreach/map milestones (`lifecycle_events.py` + `graph.py`).
- **MAP kwargs:** `run_map_verification` accepts optional linkage (`correlation_id`, `prospecting_run_id`, `account_id`, …); UI bridge passes these from Promote-to-MAP session state.
- **Errors:** Permission/runtime helpers in `app.py`; DLQ/`log_failure` receives **redacted** context (`sanitize.redact_context_for_persistence`).
- **Contract runtime:** Unsupported `schema_version` raises `ContractVersionError` / Pydantic validation and emits `contract_version_mismatch` telemetry.

**Residual edge cases**

- **Telemetry values:** Metadata **keys** are sanitized; **values** are not recursively redacted—nested structures could theoretically carry sensitive strings if a caller misuses `metadata` (see `Review_Feedback.md` R-008).
- **LLM calls:** Provider modules use SDK defaults for timeouts/retries; not uniformly aligned with `connector_policy` matrix (policy is documented + partially wired to telemetry/context timeout).

---

## Pillar 3 — Style and local flavor

- Consistent `from __future__ import annotations`, typing, and layered packages.
- **Naming:** Distinguish `src/orchestrator/router.py` (`route_task` heuristic) from `src/providers/router.py` (`ModelRouter` for LLMs).
- **`app.py`** remains very large (~1690 lines) — candidate for extraction into `src/ui/pages/` or similar (non-blocking).

---

## Pillar 4 — Security audit

- **Secrets:** `.env` gitignored; `.env.example` placeholders; no live keys in source.
- **RBAC:** `rbac.py` + `resolve_role`; production env forces effective role constraints; **documented** as demo-only UI role selection (README / architecture doc).
- **MAP handoff paths:** `safe_handoff_filename_component` + `assert_resolved_path_under_base` for archive/review writes; **atomic** JSON writes via `atomic_io.py`.
- **Telemetry:** `_sanitize_metadata` strips forbidden **keys** and key-like substrings; HTML badges/chips use `html.escape` in `components.py` for dynamic text.
- **DLQ/incidents:** Context redacted before append.
- **`unsafe_allow_html`:** Limited to badge/chip helpers with escaped dynamic content — residual risk if future edits bypass helpers.

---

## Pillar 5 — Testability

- **316 tests** cover orchestrators, safety paths, contract compat, connector policy, atomic IO, circuit telemetry, map handoff, shadow, telemetry, UI components, DQ, queue, etc.
- **Gaps:** No automated E2E for full Streamlit flows (`app.py`); manual QA remains primary for UI regressions. Eval scripts (`eval/`) are offline drift/shadow tools—not asserted as CI gates in-repo.

---

## Pillars 6–10 (extended)

| Area | Assessment |
|------|------------|
| **6 — Operational reliability** | Connector policy registry + env overrides; atomic handoff writes; circuit breaker emits `circuit_state` events. LLM HTTP timeouts not explicitly set in provider classes. |
| **7 — Data governance** | `retention.py` + admin UI; lineage/export provenance fields on exports. |
| **8 — Contracts vs docs** | `integration_contracts.md`, `ingest_contract.md`, `connector_policies.md` align broadly with `export.py`, `contract_compat.py`, `connector_policy.py`; re-verify when bumping schema versions. |
| **9 — Shadow** | `compare_map` / `compare_prospecting` require explicit `actor_role`; structural compare strips audit + lifecycle keys. |
| **10 — Static quality** | `pytest` green; `ruff check src` clean per project convention. |

---

## Mechanical checks (summary)

- No bare `except:` in `src/`.
- No `eval(` / unsafe `pickle` / `shell=True` patterns flagged in quick grep of Python sources.
- `TODO|FIXME|XXX`: no production TODO debt in `src/` beyond benign docstring text.
