from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator.shadow import compare_map, compare_prospecting


def test_compare_map_golden_samples() -> None:
    items = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    for row in items:
        r = compare_map(row["evidence_id"], row["text"], actor_role="admin")
        assert r["directional_match"] is True
        assert r["structural_match"] is True


def test_compare_prospecting_first_account() -> None:
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    r = compare_prospecting(accounts[0], actor_role="admin")
    assert "production" in r and "shadow" in r
    assert r["structural_match"] is True
    assert r["directional_match"] is True
