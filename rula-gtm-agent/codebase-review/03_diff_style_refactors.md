# Diff-Style and Low-Risk Refactors

**Review execution date:** 2026-04-11. Optional quality improvements; none block the current test suite (**316 passed**).

## Completed since prior review (reference)

1. **Path-safe filename components** — Implemented in `src/safety/paths.py` (`safe_handoff_filename_component`) and used by MAP handoff.
2. **Shadow `actor_role`** — `compare_map` / `compare_prospecting` require explicit `actor_role`.
3. **Telemetry metadata key policy** — `_sanitize_metadata` in `events.py` + tests.
4. **Stray directory** — Removed (R-006).
5. **Ruff** — Optional dev config in `pyproject.toml`; `ruff check src` passes.

## Remaining small refactors

1. **Telemetry metadata values**  
   - Optionally redact or stringify nested structures under known-safe allowlist; or document “metadata values must not contain PII” and audit call sites (ties to R-008).

2. **Provider timeouts**  
   - Pass explicit timeouts from `get_connector_policy(LLM_PROVIDER)` into Anthropic/Google client configuration where the SDK supports it (ties to R-009).

3. **`app.py` decomposition**  
   - Extract slide renderers (`_page_prospecting`, MAP slides, Insights) into `src/ui/pages/*.py` to reduce merge conflict surface and enable slimmer unit tests of pure helpers.

4. **`ruff check tests`**  
   - Many unused-import warnings in `tests/` — optional cleanup batch (`F401`) if you want a stricter CI gate.

## Tooling (optional)

- Expand ruff rule set beyond `E9`/`F` when ready (incremental).
- `mypy` on `src/schemas` + `src/orchestrator` as a first strict slice.
