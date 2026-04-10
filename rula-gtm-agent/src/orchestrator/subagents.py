"""Subagent implementations for prospecting pipeline stages.

Each function is a self-contained stage with typed inputs/outputs,
independent error handling, and telemetry hooks.
"""
from __future__ import annotations

import logging
import time

from src.agents.prospecting.enrichment import enrich_account
from src.agents.prospecting.matcher import match_value_props_detailed
from src.integrations.ingestion import load_test_accounts_raw
from src.orchestrator.contracts import (
    EnrichmentResult,
    EnrichmentRow,
    IngestionResult,
    ScoringRow,
    SignalAttributionRecord,
    SubagentErrorEnvelope,
    ValuePropScoringResult,
)
from src.schemas.account import Account
from src.safety.sanitize import sanitize_account_payload

logger = logging.getLogger(__name__)


def run_ingestion_agent(source: str, raw_accounts: list[dict] | None = None) -> IngestionResult:
    t0 = time.monotonic()
    warnings: list[str] = []
    dropped = 0

    if source == "test_data":
        accounts = raw_accounts if raw_accounts is not None else load_test_accounts_raw()
    else:
        accounts = raw_accounts or []
        if not accounts:
            warnings.append(f"Source '{source}' returned empty list; using empty set.")

    valid: list[dict] = []
    for a in accounts:
        try:
            safe = sanitize_account_payload(a)
            Account.model_validate(safe)
            valid.append(safe)
        except Exception as e:
            dropped += 1
            warnings.append(f"Dropped account {a.get('account_id', '?')}: {e}")

    ok = len(valid) > 0
    elapsed = (time.monotonic() - t0) * 1000
    result = IngestionResult(
        ok=ok,
        source=source,
        accounts=valid,
        account_count=len(valid),
        warnings=warnings,
        dropped_count=dropped,
    )
    result.meta.started_at_ms = t0 * 1000
    result.meta.finished_at_ms = (t0 * 1000) + elapsed
    result.meta.duration_ms = elapsed
    if not ok:
        result.error = SubagentErrorEnvelope(
            code="INGEST_EMPTY",
            message="No valid accounts after ingestion",
            stage="ingestion",
            recoverable=False,
        )
    return result


def run_enrichment_agent(accounts: list[dict]) -> EnrichmentResult:
    t0 = time.monotonic()
    rows: list[EnrichmentRow] = []
    for a in accounts:
        try:
            acct = Account.model_validate(a)
            enriched = enrich_account(acct)
            rows.append(EnrichmentRow(
                account_id=acct.account_id,
                account_payload=a,
                enriched=enriched.model_dump(),
            ))
        except Exception as e:
            rows.append(EnrichmentRow(
                account_id=a.get("account_id", 0),
                account_payload=a,
                enriched={},
                row_error=SubagentErrorEnvelope(
                    code="ENRICH_FAIL",
                    message=str(e),
                    stage="enrichment",
                    recoverable=False,
                    account_id=a.get("account_id"),
                ),
            ))
    has_success = any(r.row_error is None for r in rows)
    elapsed = (time.monotonic() - t0) * 1000
    result = EnrichmentResult(ok=has_success, rows=rows)
    result.meta.started_at_ms = t0 * 1000
    result.meta.finished_at_ms = (t0 * 1000) + elapsed
    result.meta.duration_ms = elapsed
    return result


def run_scoring_agent(enrichment: EnrichmentResult) -> ValuePropScoringResult:
    from src.agents.prospecting.value_prop_scoring import SCORING_VERSION
    from src.schemas.account import EnrichedAccount

    t0 = time.monotonic()
    rows: list[ScoringRow] = []
    for erow in enrichment.rows:
        if erow.row_error:
            continue
        try:
            enriched = EnrichedAccount.model_validate(erow.enriched)
            sr = match_value_props_detailed(enriched)
            rows.append(ScoringRow(
                account_id=erow.account_id,
                matches=[m.model_dump() for m in sr.matches],
                attributions=[
                    SignalAttributionRecord(
                        signal=a.signal,
                        value_prop=a.value_prop,
                        weight=a.weight,
                        matched_text=a.matched_text,
                        source_field=a.source_field,
                    )
                    for a in sr.attributions
                ],
            ))
        except Exception as e:
            logger.warning("Scoring failed for account %s: %s", erow.account_id, e)
    elapsed = (time.monotonic() - t0) * 1000
    result = ValuePropScoringResult(
        ok=len(rows) > 0,
        scoring_version=SCORING_VERSION,
        rows=rows,
    )
    result.meta.started_at_ms = t0 * 1000
    result.meta.finished_at_ms = (t0 * 1000) + elapsed
    result.meta.duration_ms = elapsed
    return result
