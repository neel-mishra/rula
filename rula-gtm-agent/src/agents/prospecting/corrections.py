from __future__ import annotations

import json
import uuid
from pathlib import Path

from src.schemas.correction import CorrectionEvent
from src.schemas.prospecting import OutreachEmail, ProspectingOutput
from src.telemetry.events import TelemetryEvent, emit

CORRECTIONS_DIR = Path("out/corrections")


def record_correction(event: CorrectionEvent) -> CorrectionEvent:
    """Persist a correction event and emit telemetry."""
    CORRECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = CORRECTIONS_DIR / f"{event.correction_id}.json"
    path.write_text(event.model_dump_json(indent=2), encoding="utf-8")
    emit(TelemetryEvent(
        event_type="correction_recorded",
        pipeline="prospecting",
        metadata={
            "correction_id": event.correction_id,
            "account_id": str(event.account_id),
            "field_edited": event.field_edited,
            "correction_type": event.correction_type,
        },
    ))
    return event


def apply_ae_edit(
    output: ProspectingOutput,
    field: str,
    new_value: str,
    actor: str = "ae",
    reason: str = "",
) -> tuple[ProspectingOutput, CorrectionEvent]:
    """Apply an AE edit to a prospecting output and record it.

    Supported fields: subject_line, body, cta, discovery_questions.
    For discovery_questions, new_value is a JSON array of strings.
    """
    old_email = output.email
    correction_id = str(uuid.uuid4())

    if field == "subject_line":
        before = old_email.subject_line
        new_email = OutreachEmail(subject_line=new_value, body=old_email.body, cta=old_email.cta)
        output = output.model_copy(update={"email": new_email})
    elif field == "body":
        before = old_email.body
        new_email = OutreachEmail(subject_line=old_email.subject_line, body=new_value, cta=old_email.cta)
        output = output.model_copy(update={"email": new_email})
    elif field == "cta":
        before = old_email.cta
        new_email = OutreachEmail(subject_line=old_email.subject_line, body=old_email.body, cta=new_value)
        output = output.model_copy(update={"email": new_email})
    elif field == "discovery_questions":
        before = json.dumps(output.discovery_questions)
        questions = json.loads(new_value) if isinstance(new_value, str) else new_value
        output = output.model_copy(update={"discovery_questions": questions})
    else:
        raise ValueError(f"Unsupported field for correction: {field}")

    event = CorrectionEvent(
        correction_id=correction_id,
        account_id=output.account_id,
        field_edited=field,
        before=before,
        after=new_value,
        edited_by=actor,
        reason=reason,
        correction_type="ae_edit",
    )
    record_correction(event)
    return output, event


def list_corrections(account_id: int) -> list[CorrectionEvent]:
    """List all recorded corrections for an account."""
    if not CORRECTIONS_DIR.exists():
        return []
    results = []
    for path in CORRECTIONS_DIR.glob("*.json"):
        try:
            event = CorrectionEvent.model_validate_json(path.read_text(encoding="utf-8"))
            if event.account_id == account_id:
                results.append(event)
        except Exception:
            continue
    return sorted(results, key=lambda e: e.edited_at)
