from __future__ import annotations

from src.orchestrator.graph import run_map_verification, run_prospecting
from src.schemas.map_verification import VerificationOutput
from src.schemas.prospecting import ProspectingOutput

_AUDIT_KEYS = frozenset(
    {"judge_pass", "judge_audit_score", "correction_attempts_used", "judge_reasoning"}
)
# Per-run UUIDs differ between shadow/production passes — omit from structural diff.
_LIFECYCLE_KEYS = frozenset(
    {
        "correlation_id",
        "prospecting_run_id",
        "map_run_id",
        "assignment_id",
        "opportunity_id",
        "outreach_message_id",
        "thread_id",
        "account_id",
    }
)


def _strip_audit_fields(d: dict) -> dict:
    skip = _AUDIT_KEYS | _LIFECYCLE_KEYS
    return {k: v for k, v in d.items() if k not in skip}


def compare_map(evidence_id: str, evidence_text: str, *, actor_role: str) -> dict:
    """
    Run MAP verification twice: production (audit on) vs shadow (audit off).
    No external CRM writes; in-memory only aside from existing lineage hooks.
    """
    production: VerificationOutput = run_map_verification(
        evidence_id, evidence_text, enable_audit=True, actor_role=actor_role,
    )
    shadow: VerificationOutput = run_map_verification(
        evidence_id, evidence_text, enable_audit=False, actor_role=actor_role,
    )
    directional = production.confidence_tier == shadow.confidence_tier
    structural = _strip_audit_fields(production.model_dump()) == _strip_audit_fields(
        shadow.model_dump()
    )
    return {
        "production": production.model_dump(),
        "shadow": shadow.model_dump(),
        "directional_match": directional,
        "structural_match": structural,
    }


def compare_prospecting(account_payload: dict, *, actor_role: str) -> dict:
    production: ProspectingOutput = run_prospecting(account_payload, enable_audit=True, actor_role=actor_role)
    shadow: ProspectingOutput = run_prospecting(account_payload, enable_audit=False, actor_role=actor_role)
    directional = production.human_review_needed == shadow.human_review_needed
    structural = _strip_audit_fields(production.model_dump()) == _strip_audit_fields(
        shadow.model_dump()
    )
    return {
        "production": production.model_dump(),
        "shadow": shadow.model_dump(),
        "directional_match": directional,
        "structural_match": structural,
    }
