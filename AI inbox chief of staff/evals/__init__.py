"""Eval-suite package.

Curated adversarial fixtures + the gold-eval pipeline live here. The
gold dataset itself is sourced from real inboxes via
`core.gold_eval.adapter.load_latest_active_dataset` once Gmail OAuth
+ connectors are live in production.
"""

from core.gold_eval.adapter import load_latest_active_dataset

__all__ = ["load_latest_active_dataset"]
