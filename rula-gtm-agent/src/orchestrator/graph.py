from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from src.agents.audit.correction import apply_map_correction, apply_prospecting_corrections
from src.agents.audit.judge import judge_map_verification, judge_prospecting
from src.agents.prospecting.dq_policy import evaluate_dq_policy
from src.agents.prospecting.enrichment import enrich_account
from src.agents.prospecting.matcher import match_value_props
from src.agents.prospecting.generator import generate_outreach
from src.agents.prospecting.evaluator import evaluate_output
from src.agents.verification.account_profile import build_company_profile_text
from src.agents.verification.committer_resolver import resolve_committer
from src.agents.verification.parser import parse_evidence
from src.agents.verification.flagger import flag_actions
from src.config import load_config
from src.context.business_context import BusinessContextRegistry
from src.context.feedback_memory import append_entry
from src.security.rbac import require_permission
from src.safety.circuit import map_breaker, prospecting_breaker
from src.safety.dlq import log_failure
from src.safety.kill_switch import map_disabled, prospecting_disabled
from src.safety.sanitize import sanitize_account_payload, sanitize_evidence_id, sanitize_evidence_text
from src.schemas.account import Account
from src.schemas.lineage import LineageRecord
from src.schemas.map_verification import VerificationOutput
from src.schemas.prospecting import ProspectingOutput
from src.telemetry.events import TelemetryEvent, emit
from src.telemetry.lifecycle_events import (
    ACCOUNT_ASSIGNED,
    COMMITMENT_EVIDENCE_CAPTURED,
    MAP_VERIFICATION_COMPLETED,
    OUTREACH_GENERATED,
    OUTREACH_SENT,
    emit_lifecycle,
)

MAX_AUDIT_RETRIES = 2


def _attach_prospecting_lifecycle(out: ProspectingOutput, trace_id: str, account: Account) -> ProspectingOutput:
    return out.model_copy(
        update={
            "correlation_id": trace_id,
            "prospecting_run_id": trace_id,
            "assignment_id": account.assignment_id,
            "opportunity_id": account.opportunity_id,
            "outreach_message_id": account.outreach_message_id,
            "thread_id": account.thread_id,
        }
    )


def _write_lineage(trace_id: str, step: str, details: dict) -> None:
    out = Path("lineage.jsonl")
    record = LineageRecord(
        trace_id=trace_id, step=step, timestamp=LineageRecord.now_iso(), details=details
    )
    out.write_text("", encoding="utf-8") if not out.exists() else None
    with out.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def run_prospecting(
    account_payload: dict, *, enable_audit: bool = True, actor_role: str = "system"
) -> ProspectingOutput:
    require_permission(actor_role, "prospecting:run")
    if prospecting_disabled():
        raise RuntimeError("Prospecting disabled (set RULA_DISABLE_PROSPECTING).")
    if not prospecting_breaker.allow():
        raise RuntimeError("Prospecting circuit breaker open; retry after recovery window.")
    trace_id = str(uuid.uuid4())
    safe = sanitize_account_payload(account_payload)

    cfg = load_config()
    ctx_meta: dict[str, str] = {}
    if cfg.business_dna_enabled:
        try:
            ctx_reg = BusinessContextRegistry.get()
            ctx_meta = ctx_reg.telemetry_metadata()
        except Exception:
            ctx_meta = {"context_loaded": "False", "context_error": "load_failed"}

    t0 = time.monotonic()
    try:
        account = Account.model_validate(safe)
        emit_lifecycle(
            ACCOUNT_ASSIGNED,
            pipeline="prospecting",
            metadata={
                "account_id": str(account.account_id),
                "correlation_id": trace_id,
            },
        )
        _write_lineage(trace_id, "prospecting.input", {"account_id": account.account_id, **ctx_meta})
        enriched = enrich_account(account)
        _write_lineage(trace_id, "prospecting.enrichment", enriched.model_dump())

        dq_eval = evaluate_dq_policy(enriched)
        if dq_eval.action == "soft_flag" and dq_eval.soft_flags:
            enriched = enriched.model_copy(
                update={
                    "flags": list(dict.fromkeys(list(enriched.flags) + dq_eval.soft_flags)),
                }
            )
        if dq_eval.action == "block_generation":
            rule_id = dq_eval.matched_rule_id or "dq_policy"
            from src.schemas.prospecting import GenerationMeta, OutreachEmail

            skip_out = ProspectingOutput(
                account_id=account.account_id,
                matched_value_props=[],
                email=OutreachEmail(
                    subject_line="[Skipped — data quality policy]",
                    body="Generation was skipped per configured data-quality rules.",
                    cta="",
                ),
                discovery_questions=[],
                quality_score=0.0,
                human_review_needed=False,
                skipped=True,
                skip_reasons=[rule_id],
                flags=list(enriched.flags),
                generation_meta=GenerationMeta(),
            )
            skip_out = _attach_prospecting_lifecycle(skip_out, trace_id, account)
            emit_lifecycle(
                OUTREACH_GENERATED,
                pipeline="prospecting",
                metadata={
                    "account_id": str(account.account_id),
                    "correlation_id": trace_id,
                    "prospecting_run_id": trace_id,
                    "skipped": "true",
                },
            )
            _write_lineage(trace_id, "prospecting.output", skip_out.model_dump())
            prospecting_breaker.record_success()
            elapsed = (time.monotonic() - t0) * 1000
            emit(
                TelemetryEvent(
                    event_type="prospecting_skipped_dq",
                    pipeline="prospecting",
                    duration_ms=elapsed,
                    success=True,
                    metadata={
                        "trace_id": trace_id,
                        "account_id": str(account.account_id),
                        "rule_id": rule_id,
                        **ctx_meta,
                    },
                )
            )
            emit(
                TelemetryEvent(
                    event_type="pipeline_complete",
                    pipeline="prospecting",
                    duration_ms=elapsed,
                    success=True,
                    metadata={"trace_id": trace_id, "account_id": account.account_id, **ctx_meta},
                )
            )
            return skip_out

        matches = match_value_props(enriched)
        _write_lineage(trace_id, "prospecting.matcher", {"top": matches[0].value_prop})
        email, questions, gen_prov = generate_outreach(enriched, matches)
        score, human_review, flags = evaluate_output(enriched, email, matches)
        from src.schemas.prospecting import GenerationMeta
        gen_meta = GenerationMeta(
            context_source=gen_prov.context_source,
            context_snippet=gen_prov.context_snippet,
            context_url=gen_prov.context_url,
            segment_label=gen_prov.segment_label,
            emphasis_vp=gen_prov.emphasis_vp,
            competitor_token=gen_prov.competitor_token,
            wedge=gen_prov.wedge,
            email_provider=gen_prov.email_provider,
            email_prompt_version=gen_prov.email_prompt_version,
            email_validation_passed=gen_prov.email_validation_passed,
            email_repair_attempted=gen_prov.email_repair_attempted,
            email_fallback_used=gen_prov.email_fallback_used,
            questions_provider=gen_prov.questions_provider,
            questions_prompt_version=gen_prov.questions_prompt_version,
            questions_validation_passed=gen_prov.questions_validation_passed,
            questions_repair_attempted=gen_prov.questions_repair_attempted,
            questions_fallback_used=gen_prov.questions_fallback_used,
            policy_flags=list(gen_prov.flags),
        )
        output = ProspectingOutput(
            account_id=account.account_id,
            matched_value_props=matches[:3],
            email=email,
            discovery_questions=questions,
            quality_score=score,
            human_review_needed=human_review,
            flags=list(dict.fromkeys(enriched.flags + flags)),
            generation_meta=gen_meta,
        )
        attempts = 0
        j = None
        if enable_audit:
            j = judge_prospecting(output, account, enriched)
            _write_lineage(trace_id, "prospecting.judge.initial", j.model_dump())
            while not j.pass_audit and attempts < MAX_AUDIT_RETRIES:
                attempts += 1
                output = apply_prospecting_corrections(enriched, matches, output, j)
                _write_lineage(
                    trace_id,
                    f"prospecting.correction.{attempts}",
                    {"suggestions": j.correction_suggestions, "output": output.model_dump()},
                )
                j = judge_prospecting(output, account, enriched)
                _write_lineage(trace_id, f"prospecting.judge.after_{attempts}", j.model_dump())
            assert j is not None
            output = output.model_copy(
                update={
                    "judge_pass": j.pass_audit,
                    "judge_audit_score": j.audit_score,
                    "correction_attempts_used": attempts,
                    "judge_reasoning": j.reasoning,
                }
            )
            append_entry(
                trace_id=trace_id,
                pipeline="prospecting",
                judge_pass=j.pass_audit,
                audit_score=j.audit_score,
                correction_attempts=attempts,
                reasoning=j.reasoning,
                extra={"account_id": account.account_id},
            )
        output = _attach_prospecting_lifecycle(output, trace_id, account)
        emit_lifecycle(
            OUTREACH_GENERATED,
            pipeline="prospecting",
            metadata={
                "account_id": str(account.account_id),
                "correlation_id": trace_id,
                "prospecting_run_id": trace_id,
                "skipped": "false",
            },
        )
        emit_lifecycle(
            OUTREACH_SENT,
            pipeline="prospecting",
            metadata={
                "account_id": str(account.account_id),
                "correlation_id": trace_id,
                "simulated": "true",
            },
        )
        _write_lineage(trace_id, "prospecting.output", output.model_dump())
        prospecting_breaker.record_success()
        elapsed = (time.monotonic() - t0) * 1000
        emit(TelemetryEvent(
            event_type="pipeline_complete",
            pipeline="prospecting",
            duration_ms=elapsed,
            success=True,
            metadata={"trace_id": trace_id, "account_id": account.account_id, **ctx_meta},
        ))
        return output
    except Exception as e:
        prospecting_breaker.record_failure()
        elapsed = (time.monotonic() - t0) * 1000
        emit(TelemetryEvent(
            event_type="pipeline_complete",
            pipeline="prospecting",
            duration_ms=elapsed,
            success=False,
            error=repr(e),
            metadata={"trace_id": trace_id, **ctx_meta},
        ))
        log_failure(
            pipeline="prospecting",
            error=e,
            context={"trace_id": trace_id, "account_id": safe.get("account_id")},
        )
        raise


def run_map_verification(
    evidence_id: str,
    evidence_text: str,
    *,
    enable_audit: bool = True,
    actor_role: str = "system",
    correlation_id: str | None = None,
    prospecting_run_id: str | None = None,
    account_id: int | None = None,
    assignment_id: str | None = None,
    opportunity_id: str | None = None,
    outreach_message_id: str | None = None,
    thread_id: str | None = None,
) -> VerificationOutput:
    require_permission(actor_role, "map:run")
    if map_disabled():
        raise RuntimeError("MAP verification disabled (set RULA_DISABLE_MAP).")
    if not map_breaker.allow():
        raise RuntimeError("MAP circuit breaker open; retry after recovery window.")
    trace_id = str(uuid.uuid4())
    eid = sanitize_evidence_id(evidence_id)
    etext = sanitize_evidence_text(evidence_text)

    cfg = load_config()
    ctx_meta_map: dict[str, str] = {}
    if cfg.business_dna_enabled:
        try:
            ctx_reg = BusinessContextRegistry.get()
            ctx_meta_map = ctx_reg.telemetry_metadata()
        except Exception:
            ctx_meta_map = {"context_loaded": "False", "context_error": "load_failed"}

    t0 = time.monotonic()
    try:
        _write_lineage(trace_id, "map.input", {"evidence_id": eid, **ctx_meta_map})
        parsed = parse_evidence(eid, etext)
        profile_txt = build_company_profile_text(account_id)
        ce = resolve_committer(etext, profile_txt)
        parsed = parsed.model_copy(update={"committer_name": ce.name, "committer_title": ce.title})
        emit_lifecycle(
            COMMITMENT_EVIDENCE_CAPTURED,
            pipeline="map_verification",
            metadata={
                "evidence_id": eid,
                "correlation_id": trace_id,
                "map_run_id": trace_id,
            },
        )
        _write_lineage(trace_id, "map.parser", parsed.model_dump())
        from src.agents.verification.scorer import score_commitment_detailed
        from dataclasses import asdict
        detailed = score_commitment_detailed(parsed)
        score, tier, risks = detailed.score, detailed.tier, list(detailed.risks)
        if parsed.source_directness != "first_party" and tier == "HIGH":
            tier = "MEDIUM"
            score = min(score, 74)
            risks.append("SECONDHAND_HIGH_ALERT")
        actions = flag_actions(tier, risks)
        output = VerificationOutput(
            evidence_id=eid,
            confidence_score=score,
            confidence_tier=tier,
            risk_factors=sorted(set(risks)),
            recommended_actions=actions,
            scoring_version=detailed.breakdown.scoring_version,
            score_breakdown=asdict(detailed.breakdown),
            parse_summary=parsed.model_dump(),
        )
        attempts = 0
        j = None
        if enable_audit:
            j = judge_map_verification(output, etext, parsed)
            _write_lineage(trace_id, "map.judge.initial", j.model_dump())
            while not j.pass_audit and attempts < MAX_AUDIT_RETRIES:
                attempts += 1
                output = apply_map_correction(parsed, output, etext)
                _write_lineage(
                    trace_id,
                    f"map.correction.{attempts}",
                    {"output": output.model_dump()},
                )
                j = judge_map_verification(output, etext, parsed)
                _write_lineage(trace_id, f"map.judge.after_{attempts}", j.model_dump())
            assert j is not None
            output = output.model_copy(
                update={
                    "judge_pass": j.pass_audit,
                    "judge_audit_score": j.audit_score,
                    "correction_attempts_used": attempts,
                    "judge_reasoning": j.reasoning,
                }
            )
            append_entry(
                trace_id=trace_id,
                pipeline="map_verification",
                judge_pass=j.pass_audit,
                audit_score=j.audit_score,
                correction_attempts=attempts,
                reasoning=j.reasoning,
                extra={"evidence_id": eid},
            )
        cor = correlation_id or trace_id
        output = output.model_copy(
            update={
                "map_run_id": trace_id,
                "correlation_id": cor,
                "prospecting_run_id": prospecting_run_id,
                "account_id": account_id,
                "assignment_id": assignment_id,
                "opportunity_id": opportunity_id,
                "outreach_message_id": outreach_message_id,
                "thread_id": thread_id,
            }
        )
        _write_lineage(trace_id, "map.output", output.model_dump())
        map_breaker.record_success()
        elapsed = (time.monotonic() - t0) * 1000
        emit(TelemetryEvent(
            event_type="pipeline_complete",
            pipeline="map_verification",
            duration_ms=elapsed,
            success=True,
            metadata={"trace_id": trace_id, "evidence_id": eid, **ctx_meta_map},
        ))
        emit_lifecycle(
            MAP_VERIFICATION_COMPLETED,
            pipeline="map_verification",
            metadata={
                "evidence_id": eid,
                "map_run_id": trace_id,
                "correlation_id": cor,
                "prospecting_run_id": prospecting_run_id or "",
            },
        )
        return output
    except Exception as e:
        map_breaker.record_failure()
        elapsed = (time.monotonic() - t0) * 1000
        emit(TelemetryEvent(
            event_type="pipeline_complete",
            pipeline="map_verification",
            duration_ms=elapsed,
            success=False,
            error=repr(e),
            metadata={"trace_id": trace_id, "evidence_id": eid, **ctx_meta_map},
        ))
        log_failure(
            pipeline="map_verification",
            error=e,
            context={"trace_id": trace_id, "evidence_id": eid},
        )
        raise


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
