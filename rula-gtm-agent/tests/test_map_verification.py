from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator.graph import run_map_verification


def test_map_tiers_match_case_expectations() -> None:
    items = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    outputs = {i["evidence_id"]: run_map_verification(i["evidence_id"], i["text"]) for i in items}
    assert outputs["A"].confidence_tier == "HIGH"
    assert outputs["B"].confidence_tier == "LOW"
    assert outputs["C"].confidence_tier == "MEDIUM"


def test_evidence_a_commitment_summary_maps_one_campaign_per_quarter() -> None:
    text = (
        "Email from David Chen (VP, Total Rewards) to AE, February 14: Thanks for the presentation yesterday. "
        "We're excited to move forward with Rula. We'd like to plan for a launch email in Q2, "
        "followed by a benefits insert for open enrollment in Q3, and a manager wellness toolkit in Q4."
    )
    out = run_map_verification("A", text)
    parse_summary = out.parse_summary or {}
    campaigns = parse_summary.get("campaigns", [])

    observed = {(c.get("campaign_type"), c.get("quarter")) for c in campaigns}
    assert observed == {
        ("launch_email", "Q2"),
        ("benefits_insert", "Q3"),
        ("manager_toolkit", "Q4"),
    }
    assert parse_summary.get("commitment_year") is not None
    assert parse_summary.get("committer_name") == "David Chen"
    assert parse_summary.get("committer_title") == "VP, Total Rewards"


def test_map_verification_with_account_id_loads_profile_for_resolver() -> None:
    items = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    a = next(i for i in items if i["evidence_id"] == "A")
    out = run_map_verification("A", a["text"], account_id=1)
    ps = out.parse_summary or {}
    assert ps.get("committer_name") == "David Chen"
