# Review Feedback — Machine-Actionable Queue

**Review execution date:** 2026-04-11.  
**Repository:** `rula-gtm-agent/`.  
**Test baseline:** **319 passed** — [`artifacts_pytest_run.txt`](artifacts_pytest_run.txt).

## Executive layer

- **Top themes:** (1) Prior **R-001–R-007** remediations are in place for path safety, RBAC documentation, shadow defaults, telemetry key hygiene, HTML escaping, stray cleanup, and ruff on `src/`. (2) **R-008–R-011 (2026-04-11 follow-ups)** are **implemented**: nested telemetry value redaction, LLM SDK timeouts aligned with `LLM_PROVIDER` policy, Insights page extracted to `src/ui/pages/`, and **ruff** is clean on **`src` and `tests`**. (3) Test coverage is strong for library code; **Streamlit UI** remains mostly manual/E2E.
- **Out of scope / non-goals for blind fixes:** Rewriting vendor SDKs, full SSO implementation, or changing product scope of ghost integrations unless product requests it.

---

## Index — historical (implemented 2026-04-10)

| ID | Severity | Primary file | Pillar | Title | Status |
|----|----------|--------------|--------|--------|--------|
| R-001 | P0 | `src/integrations/map_handoff.py` | 4 | Sanitize `evidence_id` in review-queue filenames | **Done** — see `paths.py` |
| R-002 | P1 | `app.py`, `src/security/rbac.py` | 4 | Document demo-only Streamlit roles | **Done** — README / docs / docstrings |
| R-003 | P2 | `src/orchestrator/shadow.py` | 5 / 4 | Explicit `actor_role` for shadow compares | **Done** |
| R-004 | P2 | `src/telemetry/events.py` | 4 | Metadata key sanitization | **Done** |
| R-005 | P2 | `src/ui/components.py` | 4 | Escape dynamic HTML in chips/badges | **Done** |
| R-006 | P3 | repo hygiene | 3 | Stray empty directory | **Done** |
| R-007 | P3 | `pyproject.toml` | 10 | Optional ruff | **Done** |

Full implementation notes: [`R_ID_IMPLEMENTATION_SUMMARY.md`](R_ID_IMPLEMENTATION_SUMMARY.md).

---

## Index — follow-up queue (2026-04-11 review) — **completed 2026-04-10**

| ID | Severity | Primary file | Pillar | Title | Status |
|----|----------|--------------|--------|--------|--------|
| R-008 | P2 | `src/telemetry/events.py` | 4 / 7 | Harden telemetry metadata *values* (nested PII) | **Done** — recursive sanitization + tests |
| R-009 | P2 | `src/providers/claude_provider.py`, `gemini_provider.py`, `router.py` | 6 | Align LLM HTTP timeouts with connector policy | **Done** — SDK timeouts + `tests/test_provider_connector_timeouts.py` |
| R-010 | P3 | `app.py` | 5 | Optional: split UI into modules for testability | **Done** — `page_insights` → `src/ui/pages/insights.py` |
| R-011 | P3 | `tests/` | 5 | Optional: reduce ruff F401 noise in tests or scope CI | **Done** — `ruff check tests` clean (unused imports removed) |

---

### [R-008] Telemetry metadata values may still carry sensitive nested content — **Done**

- **Severity**: P2
- **Pillar**: 4 (security) + 7 (data governance)
- **Scope**: `src/telemetry/events.py` (`_sanitize_metadata`), all `emit(TelemetryEvent(...))` call sites
- **Observation**: Sanitization removes forbidden **keys** and keys matching secret substrings. **Values** are copied as-is. A buggy or future call could attach `metadata={"details": {"password": "x"}}` and persist nested secrets.
- **Recommendation**: Either recursively redact known-bad paths in dict values, stringify and truncate metadata values, or enforce a TypedDict / pydantic model for metadata at emit time. Minimum: document “no nested secrets” and add a unit test that nested forbidden keys under a parent key are stripped recursively if you implement recursion.
- **Resolution (2026-04-10):** Recursive `_sanitize_metadata_value` with depth/string caps; module docstring defines policy; `tests/test_telemetry.py` covers nested forbidden keys.
- **Acceptance criteria**:
  - Policy documented in module docstring. **Met**
  - Tests prove nested `api_key` (or similar) cannot appear in written JSONL lines. **Met**
- **Depends on**: None
- **Suggested test**: Extend `tests/test_telemetry.py` — **added**

---

### [R-009] LLM provider calls do not explicitly apply connector policy timeouts — **Done**

- **Severity**: P2
- **Pillar**: 6 (operational reliability)
- **Scope**: `src/providers/claude_provider.py`, `src/providers/gemini_provider.py`, `src/providers/router.py`, `src/integrations/connector_policy.py`
- **Observation**: `connector_policy` defines `LLM_PROVIDER` timeout defaults and surfaces policy fields on generation telemetry. Anthropic/Google SDK calls do not clearly pass an HTTP client timeout matching `policy.timeout_seconds`.
- **Recommendation**: Where SDKs support `timeout` or `http_client` options, wire `get_connector_policy(LLM_PROVIDER).timeout_seconds`. If not supported, document reliance on SDK defaults and log policy fields for operator correlation only.
- **Resolution (2026-04-10):** Anthropic client uses `timeout=policy.timeout_seconds`; Gemini uses `HttpOptions(timeout=ms)` from policy. Documented in `docs/connector_policies.md`. Mocked unit tests in `tests/test_provider_connector_timeouts.py`.
- **Acceptance criteria**:
  - Documented behavior for timeouts; or explicit timeout wired and verified with a mocked fast-fail test if feasible. **Met**
- **Depends on**: None
- **Suggested test**: New unit test with mocked provider client if added — **added**

---

### [R-010] Split `app.py` for maintainability — **Done (incremental)**

- **Severity**: P3
- **Pillar**: 5 (testability) + 3 (style)
- **Scope**: `app.py` (~1690 lines)
- **Observation**: Single file holds all Streamlit pages and helpers; harder to review and unit-test pure logic.
- **Recommendation**: Incrementally move `_render_*` / `_page_*` functions into `src/ui/pages/` (or similar) with thin `app.py` wiring.
- **Resolution (2026-04-10):** **Insights** page moved to `src/ui/pages/insights.py` (`page_insights`); `app.py` imports and calls `page_insights()`. Further pages can follow the same pattern.
- **Acceptance criteria**:
  - `pytest -q` unchanged; Streamlit entrypoint still `streamlit run app.py`. **Met**
- **Depends on**: None
- **Suggested test**: Existing integration tests; manual smoke of Prospecting + MAP + Insights

---

### [R-011] Test suite ruff cleanliness (optional) — **Done**

- **Severity**: P3
- **Pillar**: 10
- **Scope**: `tests/**/*.py`
- **Observation**: `ruff check tests` may report many `F401` unused imports — not enforced today.
- **Recommendation**: Batch-remove unused imports or exclude tests in ruff config until cleaned.
- **Resolution (2026-04-10):** Ran `ruff check tests --fix` (26 F401 fixes). **`ruff check tests`** passes alongside `ruff check src`.
- **Acceptance criteria**:
  - `ruff check tests` passes if you choose to enforce it. **Met**
- **Depends on**: None
- **Suggested test**: N/A

---

## Workflow tip

**R-008–R-011** are closed for this review cycle. For production hardening beyond the demo, prioritize **identity / IdP** and deployment-specific controls (see risk assessment).
