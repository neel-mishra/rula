from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator.graph import run_map_verification, run_prospecting


def main() -> None:
    golden = json.loads(Path("data/golden_test_set.json").read_text(encoding="utf-8"))
    evidence = {
        e["evidence_id"]: e["text"]
        for e in json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    }
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    by_id = {a["account_id"]: a for a in accounts}

    map_total = 0
    map_correct = 0
    prospect_total = 0
    prospect_correct = 0

    for item in golden:
        if item["kind"] == "map_verification":
            map_total += 1
            out = run_map_verification(item["id"], evidence[item["id"]])
            if out.confidence_tier == item["expected_tier"]:
                map_correct += 1
        elif item["kind"] == "prospecting":
            prospect_total += 1
            acc = by_id[item["account_id"]]
            out = run_prospecting(acc)
            want = item.get("expect_judge_pass", True)
            if bool(out.judge_pass) == want:
                prospect_correct += 1

    map_score = (map_correct / map_total) if map_total else 0.0
    prospect_score = (prospect_correct / prospect_total) if prospect_total else 0.0
    print(f"golden_map_accuracy={map_score:.2f}")
    print(f"golden_prospecting_audit_accuracy={prospect_score:.2f}")


if __name__ == "__main__":
    main()
