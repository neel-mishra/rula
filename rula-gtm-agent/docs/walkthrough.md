# Technical Walkthrough (v2)

## What This System Demonstrates

- AE-first prospecting workflow with deterministic and LLM-powered generation
- Source-aware ingestion (Test Data / Clay placeholder) with bulk and single-account modes
- Bulk list processing with audit-based pass/review/error classification
- One-action handoff orchestration (sequencer + CRM + review queue routing)
- Durable run archive with per-account draft snapshots at handoff time
- MAP verification with confidence tiers, threshold explainability, and guardrails
- Audit loop with bounded self-correction retries
- In-app correction capture with lineage tracking
- Full explainability: per-account per-prop signal footnotes, threshold justification, unit economics
- Safety + governance controls for production migration
- CRM-ready export with provenance tracking
- Telemetry and operational observability

## Prospecting Path (Single Account)

1. `run_prospecting()` sanitizes payload, enforces RBAC, checks kill switch and circuit breaker.
2. Enrichment computes ICP/data completeness scores and flags sparse inputs.
3. Matcher ranks value props by account signals (industry, notes, size, health plan, merger status).
4. Generator attempts LLM generation (Claude-first for email, with Gemini fallback), falls back to deterministic templates on any failure.
5. Evaluator scores quality using ICP fit, data completeness, match scores, personalization, and CTA quality.
6. Audit judge runs independent rubric; failed outputs enter max-2 correction loop.
7. Telemetry event emitted with duration and success status.
8. Final output includes audit fields, flags, and explainability context.

## Prospecting Path (Bulk)

1. AE selects data source (Test Data / Clay) and run mode (Bulk / Single).
2. `run_prospecting_bulk()` runs the full single-account pipeline for every account in the list.
3. Each row is classified as `audit_pass`, `needs_review`, or `pipeline_error`.
4. UI renders a summary (counts by outcome), per-account expanders, and a handoff panel.
5. One-click `handoff_orchestrator()` routes passes to sequencer + CRM stubs, failures to review queue, and writes a durable run archive.

## Handoff Orchestration

1. `handoff_orchestrator()` receives a `BulkRunSummary`.
2. Builds `SequencerPayload` for each passing row (contact + email draft + metadata).
3. Builds `CrmManifestRow` for each passing row (account + top value prop + quality score).
4. Writes `ReviewQueueEntry` for each review/error row to `RULA_HUMAN_REVIEW_DIR`.
5. Archives the full run (manifest, payloads, CRM manifest, review entries) to `RULA_RUN_ARCHIVE_DIR/{run_id}/`.
6. Emits granular telemetry for each destination.

## MAP Verification Path

1. `run_map_verification()` sanitizes evidence, enforces RBAC, checks kill switch and breaker.
2. Parser extracts source directness, campaigns, quarters, blockers.
3. Scorer outputs confidence score + tier with risk factors.
4. Guardrails cap secondhand-high risk (MEDIUM ceiling for secondhand sources).
5. Audit judge validates proportionality; failed outputs enter max-2 correction loop.
6. Telemetry event emitted.
7. Final output includes threshold explanation and recommended actions.

## Generative Layer

- **Model Router**: task-to-model mapping (email -> Claude, MAP synthesis -> Gemini).
- **Fallback chain**: primary model -> secondary model -> deterministic template.
- **Prompt templates**: versioned, structured prompts with system role, context, schema contract, and negative instructions.
- **Response validation**: syntactic (JSON parse, field checks) and semantic (company mention, tone, banned words).

## Explainability

- **Value prop rationale**: explains why each value prop was selected based on industry, notes, and size signals.
- **Threshold explanation**: shows tier definitions, score breakdown, and what would change the tier.
- **Unit economics**: estimates ACV from employee count and campaign type with explicit assumptions.

## Safety and Governance

- RBAC: admin/analyst/viewer permission matrix
- Input sanitization: control-character stripping and field length limits
- Kill switches: environment-based emergency pipeline disable
- Circuit breaker: in-process failure throttling with auto-recovery
- DLQ + incidents: error capture, escalation logging, and admin viewer
- Retention: timestamp-based cleanup for lineage/memory/incident artifacts

## Integration

- CRM export payloads with provenance fields (model, prompt version, validation status)
- Download actions for JSON and TXT formats
- Shadow-safe by default; live write requires promotion gates

## Validation

```bash
python -m pytest tests/ -v          # 89 tests
PYTHONPATH=. python3 eval/drift_check.py     # Golden drift check
PYTHONPATH=. python3 eval/compare_shadow.py  # Shadow parity
```
