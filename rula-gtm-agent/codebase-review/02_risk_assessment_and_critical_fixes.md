# Risk Assessment and Critical Fixes

**Review execution date:** 2026-04-11. **Updated:** 2026-04-10 (R-008–R-011 completion).

## Status of prior queue (R-001–R-007)

Items **R-001** through **R-007** from the 2026-04-10 review cycle are **implemented** (see [`R_ID_IMPLEMENTATION_SUMMARY.md`](R_ID_IMPLEMENTATION_SUMMARY.md)): path-safe handoff filenames, RBAC/auth documentation, explicit shadow `actor_role`, telemetry metadata key sanitization, HTML escaping for UI chips/badges, stray directory removal, optional ruff on `src/`.

**No open P0 items** from that batch remain for local single-operator use.

## Status of follow-up queue (R-008–R-011)

| ID | Status | Notes |
|----|--------|--------|
| R-008 | **Closed** | Nested metadata sanitization + tests (`src/telemetry/events.py`) |
| R-009 | **Closed** | LLM SDK timeouts from `LLM_PROVIDER` policy + docs + mocked tests |
| R-010 | **Closed (incremental)** | Insights page extracted to `src/ui/pages/insights.py` |
| R-011 | **Closed** | `ruff check tests` clean |

---

## High-Level Risk Assessment

**Overall: Medium** for a **local / internal prototype** with trusted operators and static or demo data.

**Escalates to High** if deployed **internet-facing or multi-tenant** without: real authentication/authorization, hardened tenant isolation, and explicit rate limits / WAF / network controls beyond LLM SDK timeouts.

### Rationale (trust boundaries)

| Boundary | Risk driver | Notes |
|----------|-------------|--------|
| LLM providers | Medium | Keys from env; user-influenced content reaches prompts—sanitize paths must stay complete; **SDK HTTP timeouts** now follow `connector_policy` for Anthropic and Google GenAI (see `docs/connector_policies.md`). |
| Local filesystem | Low–Medium | Handoff uses atomic writes + path containment checks for MAP archives/review queue; prospecting handoff uses safe patterns via shared atomic JSON helper. |
| Streamlit UI | Low–Medium | Role selector is demo-only; documented. Session state keys are numerous—logic bugs could leak one user’s staged “promote” text in shared deployments. |
| Telemetry / DLQ | Low | Key-based metadata sanitization + **recursive value sanitization** for nested dicts/lists + DLQ redaction; mis-typed metadata should not persist forbidden nested keys (R-008). |

---

## Critical / High-Priority Follow-Ups (post–R-007)

None are **release-blocking** for the current **enclosed demo** if operators accept documented limitations. For production hardening, prioritize:

| ID | Priority | Topic |
|----|----------|--------|
| ~~R-008~~ | — | ~~Recursive metadata value safety~~ — **done** |
| ~~R-009~~ | — | ~~LLM client timeouts~~ — **done** |
| Identity | P1 (product) | Replace sidebar roles with IdP-backed roles when moving beyond single-user demo |

---

## Clarifying Questions

1. **Deployment:** Single analyst laptop vs shared Streamlit server? (Affects session isolation and “Promote to MAP” staging.)
2. **Evidence IDs in production:** Always server-issued opaque IDs vs partner-supplied strings? (Affects how paranoid sanitization must be at ingress.)
3. **CI:** Should `eval/compare_shadow.py` or drift scripts become mandatory gates?

---

## Test Baseline (this execution)

- `python3 -m pytest -q` → **319 passed** — see [`artifacts_pytest_run.txt`](artifacts_pytest_run.txt)
- `python3 -m ruff check src tests` → **All checks passed**
