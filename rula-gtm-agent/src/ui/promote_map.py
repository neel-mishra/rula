"""Bridge prospecting output into MAP verification input (additive demo flow)."""
from __future__ import annotations

from typing import Any


def build_evidence_from_prospecting(account: dict[str, Any], result: dict[str, Any]) -> tuple[str, str]:
    """Return ``(evidence_id, evidence_text)`` suitable for :func:`run_map_verification`."""
    aid = int(account.get("account_id", 0))
    company = str(account.get("company", "Account"))
    email = result.get("email") or {}
    subj = str(email.get("subject_line", ""))
    body = str(email.get("body", ""))
    cta = str(email.get("cta", ""))
    pr = str(result.get("prospecting_run_id") or result.get("correlation_id") or "")
    eid = f"promote_{aid}"
    text = (
        f"[Promoted from prospecting — account {aid} ({company})]\n"
        f"[prospecting_run_id: {pr}]\n\n"
        f"Subject: {subj}\n\n{body}\n\nCTA: {cta}\n"
    )
    return eid, text
