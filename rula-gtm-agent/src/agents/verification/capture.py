from __future__ import annotations

from src.schemas.map_capture import MapCaptureInput


def map_capture_to_evidence_text(capture: MapCaptureInput) -> str:
    header = (
        f"{capture.source_type} from {capture.committer_name or 'Unknown'}"
        f" ({capture.committer_title or 'Unknown title'}): "
        f"{capture.commitment_language.strip()}"
    )
    if not capture.campaign_plan:
        return header
    plans = ", ".join([f"{p.campaign_type} in {p.quarter}" for p in capture.campaign_plan])
    blockers = f" Blockers: {', '.join(capture.blockers)}." if capture.blockers else ""
    return f"{header} Planned campaigns: {plans}.{blockers}"
