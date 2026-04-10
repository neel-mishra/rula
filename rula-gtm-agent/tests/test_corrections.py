from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.agents.prospecting.corrections import apply_ae_edit, list_corrections
from src.schemas.prospecting import OutreachEmail, ProspectingOutput, ValuePropMatch


def _sample_output() -> ProspectingOutput:
    return ProspectingOutput(
        account_id=1,
        matched_value_props=[
            ValuePropMatch(value_prop="total_cost_of_care", score=80, reasoning="test"),
        ],
        email=OutreachEmail(
            subject_line="Original subject",
            body="Original body",
            cta="Original CTA",
        ),
        discovery_questions=["Q1?", "Q2?"],
        quality_score=4.0,
        human_review_needed=False,
    )


def test_apply_ae_edit_subject() -> None:
    output = _sample_output()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.agents.prospecting.corrections.CORRECTIONS_DIR", Path(tmpdir)):
            new_output, event = apply_ae_edit(output, "subject_line", "New subject", actor="ae")
    assert new_output.email.subject_line == "New subject"
    assert new_output.email.body == "Original body"
    assert event.field_edited == "subject_line"
    assert event.before == "Original subject"
    assert event.after == "New subject"
    assert event.correction_type == "ae_edit"


def test_apply_ae_edit_body() -> None:
    output = _sample_output()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.agents.prospecting.corrections.CORRECTIONS_DIR", Path(tmpdir)):
            new_output, event = apply_ae_edit(output, "body", "New body")
    assert new_output.email.body == "New body"
    assert event.field_edited == "body"


def test_apply_ae_edit_cta() -> None:
    output = _sample_output()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.agents.prospecting.corrections.CORRECTIONS_DIR", Path(tmpdir)):
            new_output, event = apply_ae_edit(output, "cta", "New CTA")
    assert new_output.email.cta == "New CTA"


def test_apply_ae_edit_discovery_questions() -> None:
    output = _sample_output()
    new_qs = json.dumps(["Updated Q1?", "Updated Q2?", "New Q3?"])
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.agents.prospecting.corrections.CORRECTIONS_DIR", Path(tmpdir)):
            new_output, event = apply_ae_edit(output, "discovery_questions", new_qs)
    assert len(new_output.discovery_questions) == 3
    assert new_output.discovery_questions[0] == "Updated Q1?"


def test_list_corrections_empty() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.agents.prospecting.corrections.CORRECTIONS_DIR", Path(tmpdir)):
            assert list_corrections(999) == []


def test_list_corrections_returns_matching() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.agents.prospecting.corrections.CORRECTIONS_DIR", Path(tmpdir)):
            output = _sample_output()
            apply_ae_edit(output, "subject_line", "Edit 1")
            apply_ae_edit(output, "body", "Edit 2")
            corrections = list_corrections(1)
    assert len(corrections) == 2
    assert corrections[0].field_edited == "subject_line"
    assert corrections[1].field_edited == "body"
