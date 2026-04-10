from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator.graph import run_prospecting


def main() -> None:
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    outputs = [run_prospecting(a).model_dump() for a in accounts]
    no_human_review = sum(1 for o in outputs if not o["human_review_needed"])
    adoption_proxy = no_human_review / len(outputs)
    print(f"prospecting_no_review_ratio={adoption_proxy:.2f}")


if __name__ == "__main__":
    main()
