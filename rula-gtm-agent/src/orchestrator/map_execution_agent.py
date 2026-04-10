"""MAP execution agent — thin orchestrator wrapping parse → score → flag → audit
with correlation IDs and stage-level error collection."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict

from src.agents.verification.flagger import flag_actions
from src.agents.verification.parser import parse_evidence
from src.agents.verification.scorer import score_commitment_detailed
from src.orchestrator.contracts import SubagentErrorEnvelope, StageMeta
from src.orchestrator.map_contracts import (
    MapAuditResult,
    MapExecutionRunResult,
    MapFlagResult,
    MapParseResult,
    MapScoreResult,
)
from src.telemetry.events import TelemetryEvent, emit

logger = logging.getLogger(__name__)


def _now_ms() -> float:
    return time.monotonic() * 1000


def execute_map_verification(
    evidence_id: str,
    evidence_text: str,
    *,
    actor_role: str = "user",
) -> MapExecutionRunResult:
    """Run the MAP pipeline through contract-wrapped stages."""
    run_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    result = MapExecutionRunResult(run_id=run_id, correlation_id=correlation_id)
    stage_errors: list[SubagentErrorEnvelope] = []

    # -- Parse --
    t0 = _now_ms()
    try:
        parsed = parse_evidence(evidence_id, evidence_text)
        t1 = _now_ms()
        result.parse = MapParseResult(
            meta=StageMeta(
                stage="parse", run_id=run_id, correlation_id=correlation_id,
                started_at_ms=t0, finished_at_ms=t1, duration_ms=t1 - t0,
            ),
            evidence_id=evidence_id,
            parsed=parsed.model_dump(),
        )
        result.milestones["parse"] = "ok"
    except Exception as exc:
        t1 = _now_ms()
        err = SubagentErrorEnvelope(
            code="PARSE_FAILED", message=str(exc), stage="parse", recoverable=False,
        )
        result.parse = MapParseResult(
            meta=StageMeta(
                stage="parse", run_id=run_id, correlation_id=correlation_id,
                started_at_ms=t0, finished_at_ms=t1, duration_ms=t1 - t0,
            ),
            ok=False, error=err,
        )
        result.ok = False
        result.fatal_error = err
        stage_errors.append(err)
        result.stage_errors = stage_errors
        return result

    # -- Score --
    t0 = _now_ms()
    try:
        detailed = score_commitment_detailed(parsed)
        score, tier, risks = detailed.score, detailed.tier, list(detailed.risks)
        if parsed.source_directness != "first_party" and tier == "HIGH":
            tier = "MEDIUM"
            score = min(score, 74)
            risks.append("SECONDHAND_HIGH_ALERT")
        t1 = _now_ms()
        result.score = MapScoreResult(
            meta=StageMeta(
                stage="score", run_id=run_id, correlation_id=correlation_id,
                started_at_ms=t0, finished_at_ms=t1, duration_ms=t1 - t0,
            ),
            score=score, tier=tier, risks=sorted(set(risks)),
            breakdown=asdict(detailed.breakdown),
            scoring_version=detailed.breakdown.scoring_version,
        )
        result.milestones["score"] = "ok"
    except Exception as exc:
        t1 = _now_ms()
        err = SubagentErrorEnvelope(
            code="SCORE_FAILED", message=str(exc), stage="score", recoverable=False,
        )
        result.score = MapScoreResult(
            meta=StageMeta(
                stage="score", run_id=run_id, correlation_id=correlation_id,
                started_at_ms=t0, finished_at_ms=t1, duration_ms=t1 - t0,
            ),
            ok=False, error=err,
        )
        result.ok = False
        result.fatal_error = err
        stage_errors.append(err)
        result.stage_errors = stage_errors
        return result

    # -- Flag --
    t0 = _now_ms()
    try:
        actions = flag_actions(tier, risks)
        t1 = _now_ms()
        result.flag = MapFlagResult(
            meta=StageMeta(
                stage="flag", run_id=run_id, correlation_id=correlation_id,
                started_at_ms=t0, finished_at_ms=t1, duration_ms=t1 - t0,
            ),
            recommended_actions=actions,
        )
        result.milestones["flag"] = "ok"
    except Exception as exc:
        t1 = _now_ms()
        err = SubagentErrorEnvelope(
            code="FLAG_FAILED", message=str(exc), stage="flag", recoverable=True,
        )
        result.flag = MapFlagResult(
            meta=StageMeta(
                stage="flag", run_id=run_id, correlation_id=correlation_id,
                started_at_ms=t0, finished_at_ms=t1, duration_ms=t1 - t0,
            ),
            ok=False, error=err,
        )
        result.ok = False
        stage_errors.append(err)

    # -- Audit stage is handled by the existing judge loop in run_map_verification;
    #    this agent records a placeholder. Full audit delegation is optional. --
    result.audit = MapAuditResult(
        meta=StageMeta(
            stage="audit", run_id=run_id, correlation_id=correlation_id,
        ),
    )
    result.milestones["audit"] = "deferred_to_pipeline"

    result.stage_errors = stage_errors
    emit(TelemetryEvent(
        event_type="map_execution_agent_complete",
        pipeline="map_verification",
        metadata={
            "run_id": run_id,
            "correlation_id": correlation_id,
            "ok": str(result.ok),
            "stages_completed": ",".join(result.milestones.keys()),
        },
    ))

    return result
