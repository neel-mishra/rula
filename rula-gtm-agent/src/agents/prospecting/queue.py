"""Bulk queue ordering heuristic (GAP-P5): ICP + optional reachability hint, no extra LLM."""

from __future__ import annotations

from typing import Any

from src.agents.prospecting.enrichment import enrich_account
from src.schemas.account import Account


def _row_score(icp: int, reachability: int | None) -> float:
    """v1: 0.7 * normalized ICP + 0.3 * normalized reachability (default 50)."""
    r = float(reachability) if reachability is not None else 50.0
    return 0.7 * (icp / 100.0) + 0.3 * (r / 100.0)


def sort_accounts_by_heuristic(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pre-enrich each row and sort by descending queue score."""
    scored: list[tuple[float, dict[str, Any]]] = []
    for acct in accounts:
        acc = Account.model_validate(acct)
        enr = enrich_account(acc)
        hint = acc.reachability_hint
        s = _row_score(enr.icp_fit_score, hint)
        scored.append((s, acct))
    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored]
