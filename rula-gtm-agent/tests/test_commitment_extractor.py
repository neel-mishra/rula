from __future__ import annotations

import datetime as dt

from src.agents.verification.commitment_extractor import extract_commitments


def _pairs(result) -> set[tuple[str, str]]:
    return {(c.campaign_type, c.quarter) for c in result.commitments}


def test_evidence_a_sequenced_campaigns_map_one_per_quarter() -> None:
    text = (
        "Email from David Chen: We'd like to plan for a launch email in Q2, "
        "followed by a benefits insert for open enrollment in Q3, and a manager wellness toolkit in Q4."
    )
    result = extract_commitments(text)
    assert result.strategy == "nearest_pairing"
    assert _pairs(result) == {
        ("launch_email", "Q2"),
        ("benefits_insert", "Q3"),
        ("manager_toolkit", "Q4"),
    }
    assert len(result.commitments) == 3


def test_full_year_phrase_expands_quarters() -> None:
    text = "They commit to quarterly campaigns for the full year."
    result = extract_commitments(text)
    assert result.strategy == "full_year_pattern"
    assert {c.quarter for c in result.commitments} == {"Q1", "Q2", "Q3", "Q4"}
    assert {c.campaign_type for c in result.commitments} == {"quarterly_campaign"}


def test_month_only_phrasing_maps_to_quarter() -> None:
    text = "They want a launch email in March and a benefits insert in September."
    result = extract_commitments(text)
    assert ("launch_email", "Q1") in _pairs(result)
    assert ("benefits_insert", "Q3") in _pairs(result)


def test_dedupes_duplicate_mentions() -> None:
    text = "Launch email in Q2. Launch email in Q2."
    result = extract_commitments(text)
    assert len(result.commitments) == 1
    assert _pairs(result) == {("launch_email", "Q2")}


def test_year_inference_defaults_from_date_text_then_current_year() -> None:
    text = "Email from VP, February 14: launch email in Q2."
    result = extract_commitments(text)
    assert result.inferred_year == dt.datetime.now().year
    assert all(c.year == dt.datetime.now().year for c in result.commitments)
