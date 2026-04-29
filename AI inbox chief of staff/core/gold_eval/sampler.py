"""Deterministic stratified sampler.

Given a pool of candidates already classified into strata, return a
balanced sample respecting per-stratum target counts. Seeded so a given
extraction run is reproducible.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Callable, Iterable

from core.models.gold_sample import GoldStratum

# Default per-mailbox targets per stratum. Tuned for ~200 samples / mailbox.
DEFAULT_TARGETS: dict[GoldStratum, int] = {
    GoldStratum.NEWSLETTER: 40,
    GoldStratum.DIRECT_REPLY: 40,
    GoldStratum.UPDATE: 30,
    GoldStratum.ACTION_REQUIRED: 40,
    GoldStratum.CALENDAR: 20,
    GoldStratum.AMBIGUOUS: 30,
}


def stratified_sample(
    candidates: Iterable[Any],
    classifier: Callable[[Any], GoldStratum],
    targets: dict[GoldStratum, int] | None = None,
    seed: int = 0,
) -> dict[GoldStratum, list[Any]]:
    """
    Reservoir-style sample: walk all candidates exactly once, partition
    into strata, then take min(target, available) per stratum with a
    deterministic shuffle.
    """
    targets = targets or DEFAULT_TARGETS
    rng = random.Random(seed)

    buckets: dict[GoldStratum, list[Any]] = defaultdict(list)
    for cand in candidates:
        stratum = classifier(cand)
        buckets[stratum].append(cand)

    out: dict[GoldStratum, list[Any]] = {}
    for stratum, bucket in buckets.items():
        target = targets.get(stratum, 0)
        if target <= 0:
            out[stratum] = []
            continue
        rng.shuffle(bucket)
        out[stratum] = bucket[:target]
    # Ensure every stratum key is present (even if empty) for downstream
    # reporting consistency.
    for stratum in targets:
        out.setdefault(stratum, [])
    return out


def total_sampled(buckets: dict[GoldStratum, list[Any]]) -> int:
    return sum(len(v) for v in buckets.values())
