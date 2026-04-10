# R-ID Implementation Summary

**Date:** 2026-04-10  
**Plan:** R-ID Ordered Implementation Plan with Gates (do not edit plan file in `.cursor/plans/`)

## Regression baseline

- `python3 -m pytest -q` → **298 passed**

## Completed items

| ID | Summary |
|----|---------|
| **R-001** | Added [`src/safety/paths.py`](../src/safety/paths.py) (`safe_handoff_filename_component`, `assert_resolved_path_under_base`). MAP handoff uses safe components for archive + human review filenames; raw `evidence_id` preserved in JSON. Tests: [`tests/test_safety_paths.py`](../tests/test_safety_paths.py), extended [`tests/test_map_handoff.py`](../tests/test_map_handoff.py). |
| **R-002** | Documented demo-only Streamlit roles and production expectations in [`README.md`](../README.md), [`docs/architecture_overview.md`](../docs/architecture_overview.md), module docstring on [`src/security/rbac.py`](../src/security/rbac.py). |
| **R-003** | [`src/orchestrator/shadow.py`](../src/orchestrator/shadow.py): `compare_map` / `compare_prospecting` require explicit `actor_role`. Updated [`tests/test_shadow.py`](../tests/test_shadow.py), [`eval/compare_shadow.py`](../eval/compare_shadow.py). |
| **R-004** | [`src/telemetry/events.py`](../src/telemetry/events.py): metadata sanitization policy + `_sanitize_metadata`; tests in [`tests/test_telemetry.py`](../tests/test_telemetry.py). |
| **R-005** | [`src/ui/components.py`](../src/ui/components.py): `html.escape` for dynamic tier/score/risk chip text; tests [`tests/test_ui_components.py`](../tests/test_ui_components.py). |
| **R-006** | Removed stray empty directory `src/{orchestrator,agents/`. |
| **R-007** | [`pyproject.toml`](../pyproject.toml): optional dev dependency `ruff`, `[tool.ruff]` config (`ruff check src` passes). [`README.md`](../README.md): optional lint command. |

## Residual risks (not eliminated)

- Real authentication/authorization for production remains out of scope for this prototype; docs now state the threat model.
- Telemetry sanitization is key-based; do not add new metadata keys that embed prompts without extending policy.

## Ruff note

`ruff check --fix` was applied to **`src/`** once to clear unused imports (F401). `F841` unused-local is ignored in config to avoid churn in demo parsers.
