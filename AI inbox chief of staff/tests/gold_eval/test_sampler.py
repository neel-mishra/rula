"""Sampler unit tests — determinism + per-stratum target counts."""

from __future__ import annotations

from core.gold_eval.sampler import DEFAULT_TARGETS, stratified_sample, total_sampled
from core.models.gold_sample import GoldStratum


def _stub_classifier(item: int) -> GoldStratum:
    """Map small ints into rotating strata for test determinism."""
    strata = list(GoldStratum)
    return strata[item % len(strata)]


def test_stratified_sample_respects_targets():
    candidates = list(range(1000))
    out = stratified_sample(candidates, _stub_classifier, seed=42)
    for stratum, target in DEFAULT_TARGETS.items():
        assert len(out[stratum]) == min(target, sum(1 for c in candidates if _stub_classifier(c) == stratum))


def test_stratified_sample_seed_determinism():
    candidates = list(range(1000))
    a = stratified_sample(candidates, _stub_classifier, seed=7)
    b = stratified_sample(candidates, _stub_classifier, seed=7)
    for stratum in GoldStratum:
        assert a[stratum] == b[stratum]


def test_different_seeds_yield_different_pickings():
    candidates = list(range(1000))
    a = stratified_sample(candidates, _stub_classifier, seed=1)
    b = stratified_sample(candidates, _stub_classifier, seed=2)
    # At least one stratum should diverge under a different seed.
    diverged = any(a[s] != b[s] for s in GoldStratum if a[s])
    assert diverged


def test_total_sampled_matches_sum():
    candidates = list(range(500))
    out = stratified_sample(candidates, _stub_classifier, seed=0)
    assert total_sampled(out) == sum(len(v) for v in out.values())


def test_empty_candidates():
    out = stratified_sample([], _stub_classifier, seed=0)
    assert all(out[s] == [] for s in GoldStratum)
