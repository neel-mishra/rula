from __future__ import annotations

import json
from pathlib import Path

from src.agents.prospecting.queue import sort_accounts_by_heuristic


def test_heuristic_sort_differs_from_file_order() -> None:
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    file_ids = [a["account_id"] for a in accounts]
    sorted_accounts = sort_accounts_by_heuristic(accounts)
    heur_ids = [a["account_id"] for a in sorted_accounts]
    assert sorted(file_ids) == sorted(heur_ids)
    assert file_ids != heur_ids
