from __future__ import annotations

from src.ui.promote_map import build_evidence_from_prospecting


def test_build_evidence_contains_account_and_run_id() -> None:
    eid, text = build_evidence_from_prospecting(
        {"account_id": 7, "company": "Acme"},
        {
            "email": {"subject_line": "Hi", "body": "Body", "cta": "Reply"},
            "prospecting_run_id": "run-abc",
        },
    )
    assert eid == "promote_7"
    assert "Acme" in text
    assert "run-abc" in text
    assert "Subject: Hi" in text
