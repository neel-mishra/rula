from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.orchestrator.graph import run_map_verification, run_prospecting, save_json


def _load_json(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_demo() -> None:
    accounts = _load_json("data/accounts.json")
    evidence = _load_json("data/map_evidence.json")

    prospecting_outputs = [run_prospecting(a).model_dump() for a in accounts]
    map_outputs = [
        run_map_verification(item["evidence_id"], item["text"]).model_dump()
        for item in evidence
    ]

    save_json(Path("out/prospecting_outputs.json"), prospecting_outputs)
    save_json(Path("out/map_outputs.json"), map_outputs)
    print("Wrote out/prospecting_outputs.json and out/map_outputs.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-demo", action="store_true")
    args = parser.parse_args()
    if args.run_demo:
        run_demo()
