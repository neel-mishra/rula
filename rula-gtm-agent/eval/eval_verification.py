from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator.graph import run_map_verification


def main() -> None:
    items = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    outputs = [run_map_verification(i["evidence_id"], i["text"]).model_dump() for i in items]
    by_id = {o["evidence_id"]: o["confidence_tier"] for o in outputs}
    print(by_id)


if __name__ == "__main__":
    main()
