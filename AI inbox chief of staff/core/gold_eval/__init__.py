"""Gold-eval fixture pipeline.

Real-inbox-backed sampling, scrubbing, labeling, and adapter for the
nightly eval worker. The dataset itself is populated only after Gmail
OAuth + connectors are live; the scaffolding ships behind feature flags.

Public API:
- stratifier.classify_stratum(email_dict) -> GoldStratum
- sampler.stratified_sample(candidates, target_per_stratum, seed) -> list
- scrubber.scrub_email_for_gold(email_dict, mailbox_salt) -> dict
- adapter.load_latest_active_dataset(fixture_type) -> list[GoldSample]
"""

from core.gold_eval.adapter import load_latest_active_dataset
from core.gold_eval.sampler import stratified_sample
from core.gold_eval.scrubber import scrub_email_for_gold
from core.gold_eval.stratifier import classify_stratum

__all__ = [
    "classify_stratum",
    "stratified_sample",
    "scrub_email_for_gold",
    "load_latest_active_dataset",
]
