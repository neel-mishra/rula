"""Top-level ExecutionAgent orchestrating subagent stages.

Manages stage ordering, retry/fallback at agent boundaries,
circuit-break containment, and per-stage telemetry with correlation IDs.
"""
from __future__ import annotations

import logging
import time
import uuid

from src.orchestrator.contracts import (
    ExecutionAgentRunResult,
    SubagentErrorEnvelope,
)
from src.orchestrator.subagents import (
    run_enrichment_agent,
    run_ingestion_agent,
    run_scoring_agent,
)
from src.telemetry.events import TelemetryEvent, emit

logger = logging.getLogger(__name__)


def execute_prospecting_run(
    source: str,
    raw_accounts: list[dict] | None = None,
    *,
    actor_role: str = "user",
) -> ExecutionAgentRunResult:
    """Run the full prospecting pipeline through the subagent chain.

    Stages: Ingestion -> Enrichment -> Scoring.
    Generation and Explainability remain in the existing bulk runner
    until the LLM-dependent stages are fully migrated to subagents.
    """
    run_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    t0 = time.monotonic()

    result = ExecutionAgentRunResult(
        run_id=run_id,
        correlation_id=correlation_id,
        milestones={},
    )

    # --- Stage 1: Ingestion ---
    try:
        ingestion = run_ingestion_agent(source, raw_accounts)
        ingestion.meta.run_id = run_id
        ingestion.meta.correlation_id = correlation_id
        result.ingestion = ingestion
        if not ingestion.ok:
            result.ok = False
            result.fatal_error = ingestion.error
            _emit_stage(run_id, "ingestion", False, ingestion.meta.duration_ms)
            return result
        _emit_stage(run_id, "ingestion", True, ingestion.meta.duration_ms)
        result.milestones["ingestion"] = "complete"
    except Exception as e:
        result.ok = False
        result.fatal_error = SubagentErrorEnvelope(
            code="INGEST_CRASH", message=str(e), stage="ingestion", recoverable=False,
        )
        return result

    # --- Stage 2: Enrichment ---
    try:
        enrichment = run_enrichment_agent(ingestion.accounts)
        enrichment.meta.run_id = run_id
        enrichment.meta.correlation_id = correlation_id
        result.enrichment = enrichment
        _emit_stage(run_id, "enrichment", True, enrichment.meta.duration_ms)
        result.milestones["enrichment"] = "complete"
    except Exception as e:
        result.ok = False
        result.fatal_error = SubagentErrorEnvelope(
            code="ENRICH_CRASH", message=str(e), stage="enrichment", recoverable=False,
        )
        return result

    # --- Stage 3: Scoring ---
    try:
        scoring = run_scoring_agent(enrichment)
        scoring.meta.run_id = run_id
        scoring.meta.correlation_id = correlation_id
        result.scoring = scoring
        _emit_stage(run_id, "scoring", True, scoring.meta.duration_ms)
        result.milestones["scoring"] = "complete"
    except Exception as e:
        result.ok = False
        result.fatal_error = SubagentErrorEnvelope(
            code="SCORE_CRASH", message=str(e), stage="scoring", recoverable=False,
        )
        return result

    elapsed = (time.monotonic() - t0) * 1000
    result.milestones["prospecting_executed"] = "complete"
    logger.info("ExecutionAgent run %s completed in %.0fms", run_id, elapsed)
    return result


def _emit_stage(run_id: str, stage: str, success: bool, duration_ms: float) -> None:
    emit(TelemetryEvent(
        event_type="subagent_stage_complete",
        pipeline="prospecting",
        duration_ms=duration_ms,
        success=success,
        metadata={"run_id": run_id, "stage": stage},
    ))
