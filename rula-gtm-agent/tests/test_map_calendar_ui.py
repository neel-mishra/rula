from __future__ import annotations

from app import _build_commitment_calendar_rows


def test_build_commitment_calendar_rows_shapes_q_columns() -> None:
    parse_summary = {
        "commitment_year": 2026,
        "campaigns": [
            {"campaign_type": "launch_email", "quarter": "Q2"},
            {"campaign_type": "benefits_insert", "quarter": "Q3"},
            {"campaign_type": "manager_toolkit", "quarter": "Q4"},
        ],
    }
    year, rows = _build_commitment_calendar_rows(parse_summary)
    assert year == 2026
    assert rows
    for row in rows:
        assert set(row.keys()) == {"Initiative", "Q1", "Q2", "Q3", "Q4"}


def test_build_commitment_calendar_rows_marks_correct_cells() -> None:
    parse_summary = {
        "commitment_year": 2026,
        "campaigns": [
            {"campaign_type": "launch_email", "quarter": "Q2"},
        ],
    }
    _, rows = _build_commitment_calendar_rows(parse_summary)
    launch_row = next(r for r in rows if r["Initiative"] == "Launch Email")
    assert launch_row["Q2"] == "Committed"
    assert launch_row["Q1"] == ""
    assert launch_row["Q3"] == ""
    assert launch_row["Q4"] == ""
