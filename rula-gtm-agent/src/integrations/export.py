from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.config import load_config
from src.integrations.contract_compat import validate_lineage_export_dict
from src.schemas.evidence_artifact import LineageExportBlock

DEFAULT_MAP_CRM_STATE_LABELS = [
    "ingest.received",
    "parse.complete",
    "score.complete",
    "handoff.simulated",
]

DEFAULT_REVOPS_REVIEW_CHECKLIST = [
    "Verify evidence ID and source channel match the customer record.",
    "Confirm confidence tier aligns with commitment language and directness.",
    "Check that recommended actions are appropriate before any CRM field update.",
    "Route LOW tier or audit failures to RevOps review queue.",
]


@dataclass
class ProspectingExport:
    """CRM-ready export payload for prospecting output."""
    account_id: int
    company: str
    industry: str
    email_subject: str
    email_body: str
    email_cta: str
    discovery_questions: list[str]
    top_value_prop: str
    value_prop_rationale: str
    quality_score: float
    human_review_needed: bool
    audit_pass: bool | None
    audit_score: float | None
    content_model: str = "deterministic"
    content_prompt_version: str = "v1"
    content_validation_status: str = "passed"
    content_review_required: bool = False
    provider_primary: str = ""
    provider_fallback_used: bool = False
    confidence_caveats: list[str] = field(default_factory=list)
    context_version: str = ""
    context_hash: str = ""
    export_contract_version: str = "1"
    correlation_id: str = ""
    prospecting_run_id: str = ""
    assignment_id: str = ""
    opportunity_id: str = ""
    outreach_message_id: str = ""
    thread_id: str = ""
    lineage_export: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d.get("lineage_export") is None:
            d.pop("lineage_export", None)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class MapExport:
    """CRM-ready export payload for MAP verification output."""
    evidence_id: str
    confidence_tier: str
    confidence_score: int
    risk_factors: list[str]
    recommended_actions: list[str]
    map_threshold_rationale: str
    audit_pass: bool | None
    audit_score: float | None
    confidence_caveats: list[str] = field(default_factory=list)
    context_version: str = ""
    context_hash: str = ""
    scoring_version: str = ""
    score_breakdown: dict | None = None
    crm_handoff_state: str = "simulated"
    crm_state_labels: list[str] = field(default_factory=lambda: list(DEFAULT_MAP_CRM_STATE_LABELS))
    revops_review_checklist: list[str] = field(
        default_factory=lambda: list(DEFAULT_REVOPS_REVIEW_CHECKLIST)
    )
    export_contract_version: str = "1"
    map_run_id: str = ""
    correlation_id: str = ""
    prospecting_run_id: str = ""
    account_id: int | None = None
    assignment_id: str = ""
    opportunity_id: str = ""
    outreach_message_id: str = ""
    thread_id: str = ""
    lineage_export: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d.get("lineage_export") is None:
            d.pop("lineage_export", None)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _context_meta() -> tuple[str, str]:
    """Retrieve current context version and hash for export provenance."""
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded:
            return reg.bundle.version, reg.bundle.content_hash
    except Exception:
        pass
    return "", ""


def build_prospecting_export(
    result: dict,
    account: dict,
    *,
    lineage: LineageExportBlock | None = None,
) -> ProspectingExport:
    email = result.get("email", {})
    vps = result.get("matched_value_props", [])
    top_vp = vps[0] if vps else {}

    caveats: list[str] = []
    if result.get("human_review_needed"):
        caveats.append("Human review recommended before sending.")
    if not result.get("judge_pass"):
        caveats.append("Audit flagged for review; verify before CRM entry.")

    ctx_ver, ctx_hash = _context_meta()

    lineage_dict: dict[str, Any] | None = None
    cfg = load_config()
    if cfg.export_lineage_enabled and lineage is not None:
        lineage_dict = lineage.to_dict_omit_none()
        validate_lineage_export_dict(lineage_dict)

    return ProspectingExport(
        account_id=account.get("account_id", 0),
        company=account.get("company", ""),
        industry=account.get("industry", ""),
        email_subject=email.get("subject_line", ""),
        email_body=email.get("body", ""),
        email_cta=email.get("cta", ""),
        discovery_questions=result.get("discovery_questions", []),
        top_value_prop=top_vp.get("value_prop", ""),
        value_prop_rationale=top_vp.get("reasoning", ""),
        quality_score=result.get("quality_score", 0),
        human_review_needed=result.get("human_review_needed", False),
        audit_pass=result.get("judge_pass"),
        audit_score=result.get("judge_audit_score"),
        confidence_caveats=caveats,
        context_version=ctx_ver,
        context_hash=ctx_hash,
        correlation_id=str(result.get("correlation_id") or ""),
        prospecting_run_id=str(result.get("prospecting_run_id") or ""),
        assignment_id=str(result.get("assignment_id") or ""),
        opportunity_id=str(result.get("opportunity_id") or ""),
        outreach_message_id=str(result.get("outreach_message_id") or ""),
        thread_id=str(result.get("thread_id") or ""),
        lineage_export=lineage_dict,
    )


def build_map_export(
    result: dict,
    threshold_rationale: str = "",
    *,
    lineage: LineageExportBlock | None = None,
) -> MapExport:
    caveats: list[str] = []
    if result.get("confidence_tier") == "LOW":
        caveats.append("Low confidence: additional evidence required before pipeline update.")
    if not result.get("judge_pass"):
        caveats.append("Audit flagged for review; verify with manager.")
    risks = result.get("risk_factors", [])
    if "SECONDHAND_HIGH_ALERT" in risks:
        caveats.append("Tier capped due to secondhand source.")

    ctx_ver, ctx_hash = _context_meta()

    lineage_dict: dict[str, Any] | None = None
    cfg = load_config()
    if cfg.export_lineage_enabled and lineage is not None:
        lineage_dict = lineage.to_dict_omit_none()
        validate_lineage_export_dict(lineage_dict)

    aid = result.get("account_id")
    return MapExport(
        evidence_id=result.get("evidence_id", ""),
        confidence_tier=result.get("confidence_tier", ""),
        confidence_score=result.get("confidence_score", 0),
        risk_factors=risks,
        recommended_actions=result.get("recommended_actions", []),
        map_threshold_rationale=threshold_rationale,
        audit_pass=result.get("judge_pass"),
        audit_score=result.get("judge_audit_score"),
        confidence_caveats=caveats,
        context_version=ctx_ver,
        context_hash=ctx_hash,
        scoring_version=result.get("scoring_version", ""),
        score_breakdown=result.get("score_breakdown"),
        crm_handoff_state="simulated",
        crm_state_labels=list(DEFAULT_MAP_CRM_STATE_LABELS),
        revops_review_checklist=list(DEFAULT_REVOPS_REVIEW_CHECKLIST),
        map_run_id=str(result.get("map_run_id") or ""),
        correlation_id=str(result.get("correlation_id") or ""),
        prospecting_run_id=str(result.get("prospecting_run_id") or ""),
        account_id=int(aid) if aid is not None else None,
        assignment_id=str(result.get("assignment_id") or ""),
        opportunity_id=str(result.get("opportunity_id") or ""),
        outreach_message_id=str(result.get("outreach_message_id") or ""),
        thread_id=str(result.get("thread_id") or ""),
        lineage_export=lineage_dict,
    )
