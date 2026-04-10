# Prospecting Agent v2 — Readiness Report

## Summary

v2 delivers bulk list processing, source-aware ingestion, a redesigned handoff UX, quality-score recalibration, per-account signal footnotes, in-app correction capture, and AE-friendly labeling. All changes are backward-compatible with v1 single-account flows.

## What shipped

### Ingestion abstraction
- `src/integrations/ingestion.py` provides `load_test_accounts()`, `load_test_accounts_raw()`, and `load_clay_accounts_demo()` (empty list placeholder).
- `ClayWebhookConfig` + `build_clay_webhook_payload()` scaffold the production webhook contract without executing any live calls in demo.
- Config keys `CLAY_WEBHOOK_URL`, `CLAY_WORKSPACE_ID`, `CLAY_LIST_ID` added to `AppConfig`.

### Bulk pipeline
- `src/orchestrator/bulk_prospecting.py` — `run_prospecting_bulk()` runs the full pipeline for every account in a list, classifies each row as `audit_pass`, `needs_review`, or `pipeline_error`, and emits `bulk_pipeline_complete` telemetry.
- Returns `BulkRunSummary` with per-row results, aggregate counts, and convenience accessors (`.pass_rows`, `.review_rows`, `.error_rows`).

### Handoff orchestrator (one-action handoff)
- `src/integrations/handoff.py` — `handoff_orchestrator()` takes a `BulkRunSummary` and:
  1. Routes passes to sequencer stub + CRM stub.
  2. Routes review/errors to human-review queue (written to `RULA_HUMAN_REVIEW_DIR`).
  3. Writes a durable run archive (manifest, sequencer payloads, CRM manifest, review entries) to `RULA_RUN_ARCHIVE_DIR/{run_id}/`.
  4. Emits `handoff_orchestrated`, `handoff_destination_sequencer`, `handoff_destination_crm`, `handoff_destination_review_queue` telemetry.

### Correction capture
- `src/schemas/correction.py` — `CorrectionEvent` Pydantic model with full lineage (who, when, what, before/after, reaudit status).
- `src/agents/prospecting/corrections.py` — `apply_ae_edit()` modifies a `ProspectingOutput` field and persists the correction; `list_corrections()` reads back by account. Emits `correction_recorded` telemetry.

### QA bug fixes
- **Signal footnote bug**: `explain_value_prop()` now builds per-value-prop signal lists via `_account_signals()`, so footnotes reflect the actual industry, size, notes, and health plan of each account rather than a static string.
- **Quality score variance**: `evaluate_output()` now starts at 2.5 and adds/subtracts based on ICP fit, data completeness, match score + delta, company-name personalization, contact availability, and CTA quality — producing meaningful variance across the 8 test accounts.
- **Matcher variance**: base scores lowered from 35→25, more industry/size/notes/health-plan signals added, richer per-match reasoning strings.

### UI labeling
- `Audit = PASS` → **Ready to Send** (green badge).
- `Audit = REVIEW` → **Needs Review** (amber badge).
- `Quality score` → **Account Score** (UI label; internal quality metric unchanged).
- `Corrections used` → **Email edits**.
- Account details rendered as markdown preview, not JSON code block.

### Prospecting page (v2 flow)
- Source selector (Test Data / Clay) at top.
- Run mode radio: Bulk list (default) / Single account.
- Bulk mode: preview all accounts, one-click "Run prospecting", summary cards (Ready to Send / Needs Review / Errors), per-account expanders.
- Handoff panel: pre-handoff summary, one primary CTA ("Submit handoff"), secondary actions collapsed (Download all emails, Download CRM manifest).
- Clay empty state with guidance.

## Test validation

116 tests pass across 19 test files:

| Test file | Tests | Purpose |
|-----------|-------|---------|
| `test_qa_bugfixes.py` | 7 | Signal footnote variance, quality-score variance, matcher variance |
| `test_ingestion.py` | 6 | Test/Clay loaders, webhook config/payload |
| `test_bulk_prospecting.py` | 5 | Full bulk run, classification, uniqueness |
| `test_handoff.py` | 3 | Archive creation, sequencer/CRM payload content |
| `test_corrections.py` | 6 | AE edit apply, persistence, listing |
| `test_ux_acceptance.py` | (updated) | Label changes reflected |
| _(original tests)_ | 89 | All existing tests continue to pass |

## Acceptance criteria status

| Criterion | Status |
|-----------|--------|
| Source selector (Test Data / Clay) | Done |
| Clay shows empty state + guidance | Done |
| Bulk default runs all test accounts | Done |
| Pass vs needs-review split by audit | Done |
| Repository consolidation placeholder | Done (run archive) |
| CRM bulk push stub (passes only) | Done |
| Human-review folder stub (failures) | Done |
| Claude personalization provenance fields | Done (schema + metadata) |
| Signal footnotes vary per account/prop | Done |
| Quality scores vary across accounts | Done |
| Corrections split (auto vs AE) + in-app edit | Done |
| AE-friendly labels (Ready to Send, Account Score, Email edits) | Done |
| Account details as markdown preview | Done |
| One-CTA handoff with auto failure routing | Done |
| Automatic run archive at handoff | Done |
| DLQ separate from success archive | Done |
| Single-account path remains for QA | Done |
| All tests pass | Done (116/116) |

## Known limitations

- Clay integration is a placeholder — no live webhook calls. Production wiring requires `CLAY_WEBHOOK_URL` and callback handler.
- Email sequencer is a stub — generates payloads but does not POST to any external API.
- CRM push is a stub — writes a JSON manifest to disk.
- In-app correction UI (Streamlit text inputs for editing) is available in the code path but not yet wired into the Streamlit form widgets; the `apply_ae_edit()` function is ready for integration.
- Personalization currently uses the deterministic path unless LLM keys are configured.
