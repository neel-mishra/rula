"""Data-quality policy: optional YAML rules evaluated after enrichment (GAP-P3)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from src.config import load_config
from src.schemas.account import EnrichedAccount

logger = logging.getLogger(__name__)

Action = Literal["allow", "soft_flag", "block_generation"]


@dataclass
class DqEvaluation:
    action: Action = "allow"
    matched_rule_id: str | None = None
    soft_flags: list[str] = field(default_factory=list)


def _load_policy_raw(path: str) -> dict[str, Any] | None:
    p = Path(path)
    if not path or not p.is_file():
        return None
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception as e:
        logger.warning("DQ policy invalid or unreadable (%s): %s", path, e)
        return None


def _match_when(enriched: EnrichedAccount, when: dict[str, Any]) -> bool:
    flags = enriched.flags
    if "flag_contains" in when:
        needle = str(when["flag_contains"])
        if not any(needle in f for f in flags):
            return False
    if "icp_below" in when:
        thr = int(when["icp_below"])
        if enriched.icp_fit_score >= thr:
            return False
    if "icp_above" in when:
        thr = int(when["icp_above"])
        if enriched.icp_fit_score <= thr:
            return False
    return True


def evaluate_dq_policy(enriched: EnrichedAccount) -> DqEvaluation:
    """First matching rule wins (documented precedence). Missing/invalid policy → allow."""
    cfg = load_config()
    path = cfg.dq_policy_path
    raw = _load_policy_raw(path)
    if not raw:
        return DqEvaluation(action="allow")

    rules = raw.get("rules")
    if not isinstance(rules, list):
        logger.warning("DQ policy has no rules list; disabling DQ.")
        return DqEvaluation(action="allow")

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = str(rule.get("id", "unknown"))
        when = rule.get("when")
        action = rule.get("action", "allow")
        if not isinstance(when, dict):
            continue
        if action not in ("allow", "soft_flag", "block_generation"):
            continue
        if not _match_when(enriched, when):
            continue
        if action == "block_generation":
            return DqEvaluation(action="block_generation", matched_rule_id=rid)
        if action == "soft_flag":
            extra = rule.get("add_flags", [])
            soft = [str(x) for x in extra] if isinstance(extra, list) else []
            return DqEvaluation(action="soft_flag", matched_rule_id=rid, soft_flags=soft)
        return DqEvaluation(action="allow", matched_rule_id=rid)

    return DqEvaluation(action="allow")
