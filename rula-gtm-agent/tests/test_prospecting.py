from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator.graph import run_prospecting


def test_prospecting_outputs_schema_and_flags() -> None:
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    out = run_prospecting(accounts[4])  # Pinnacle, sparse
    assert out.account_id == 5
    assert len(out.matched_value_props) >= 1
    assert "NEEDS_CONTACT_RESEARCH" in out.flags
