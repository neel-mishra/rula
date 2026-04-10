from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator.shadow import compare_map, compare_prospecting


def main() -> None:
    evidence = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))

    map_dir = 0
    map_struct = 0
    for row in evidence:
        r = compare_map(row["evidence_id"], row["text"], actor_role="admin")
        map_dir += 1 if r["directional_match"] else 0
        map_struct += 1 if r["structural_match"] else 0

    prospect_dir = 0
    prospect_struct = 0
    for acc in accounts[:3]:
        r = compare_prospecting(acc, actor_role="admin")
        prospect_dir += 1 if r["directional_match"] else 0
        prospect_struct += 1 if r["structural_match"] else 0

    n_map = len(evidence)
    n_p = min(3, len(accounts))
    print(f"map_directional_match_rate={map_dir / n_map:.2f}")
    print(f"map_structural_match_rate={map_struct / n_map:.2f}")
    print(f"prospecting_directional_match_rate={prospect_dir / n_p:.2f}")
    print(f"prospecting_structural_match_rate={prospect_struct / n_p:.2f}")


if __name__ == "__main__":
    main()
