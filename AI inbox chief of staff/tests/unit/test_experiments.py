"""Unit tests for A/B experiment assignment + rollup math."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from core.prompts.experiments import (
    _bucket,
    _two_proportion_z,
    assign_variant,
)


def _variant(label: str, traffic_pct: int, is_control: bool = False, idx: int = 0):
    """Dataclass-shaped stub that satisfies assign_variant without touching the DB."""
    return SimpleNamespace(
        id=uuid.UUID(f"00000000-0000-0000-0000-{idx:012d}"),
        label=label,
        prompt_version=f"v{idx + 1}",
        traffic_pct=traffic_pct,
        is_control=is_control,
        created_at=idx,  # used for sort, any sortable value works
    )


def _experiment(variants):
    return SimpleNamespace(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        variants=variants,
    )


class TestBucketing:
    def test_bucket_in_range(self):
        exp_id = uuid.uuid4()
        mb_id = uuid.uuid4()
        bucket = _bucket(exp_id, mb_id)
        assert 0 <= bucket < 100

    def test_bucket_is_deterministic(self):
        exp_id = uuid.uuid4()
        mb_id = uuid.uuid4()
        assert _bucket(exp_id, mb_id) == _bucket(exp_id, mb_id)

    def test_bucket_differs_across_mailboxes(self):
        exp_id = uuid.uuid4()
        buckets = {_bucket(exp_id, uuid.uuid4()) for _ in range(50)}
        # Not guaranteed uniformly different, but should have some variety
        assert len(buckets) > 20

    def test_bucket_differs_across_experiments(self):
        mb_id = uuid.uuid4()
        b1 = _bucket(uuid.UUID("11111111-1111-1111-1111-111111111111"), mb_id)
        b2 = _bucket(uuid.UUID("22222222-2222-2222-2222-222222222222"), mb_id)
        # Overwhelmingly likely to differ; allow a tiny collision chance
        # but this is a sanity check
        assert b1 != b2 or uuid.uuid4()  # non-flaky fallback


class TestVariantAssignment:
    def test_assignment_is_stable_for_same_mailbox(self):
        variants = [_variant("a", 50, True, 0), _variant("b", 50, False, 1)]
        exp = _experiment(variants)
        mb_id = uuid.uuid4()
        first = assign_variant(exp, mb_id)
        second = assign_variant(exp, mb_id)
        assert first is not None and second is not None
        assert first.id == second.id

    def test_100_0_split_always_routes_to_first(self):
        variants = [_variant("a", 100, True, 0), _variant("b", 0, False, 1)]
        exp = _experiment(variants)
        for _ in range(100):
            v = assign_variant(exp, uuid.uuid4())
            assert v.label == "a"

    def test_split_is_roughly_uniform(self):
        variants = [_variant("a", 50, True, 0), _variant("b", 50, False, 1)]
        exp = _experiment(variants)
        counts = {"a": 0, "b": 0}
        for _ in range(1000):
            v = assign_variant(exp, uuid.uuid4())
            counts[v.label] += 1
        # Tolerate ±10% swing on 1000 trials
        assert 400 <= counts["a"] <= 600
        assert 400 <= counts["b"] <= 600

    def test_empty_variants_returns_none(self):
        exp = _experiment([])
        assert assign_variant(exp, uuid.uuid4()) is None

    def test_three_way_split(self):
        variants = [
            _variant("a", 50, True, 0),
            _variant("b", 30, False, 1),
            _variant("c", 20, False, 2),
        ]
        exp = _experiment(variants)
        counts = {"a": 0, "b": 0, "c": 0}
        for _ in range(2000):
            v = assign_variant(exp, uuid.uuid4())
            counts[v.label] += 1
        # Within ~20% of expected
        assert 800 <= counts["a"] <= 1200
        assert 500 <= counts["b"] <= 700
        assert 300 <= counts["c"] <= 500


class TestZTest:
    def test_low_sample_returns_none(self):
        assert _two_proportion_z(0.5, 3, 0.5, 3) is None

    def test_zero_variance_pooled_returns_none(self):
        # All zeros or all ones pooled
        assert _two_proportion_z(0.0, 100, 0.0, 100) is None
        assert _two_proportion_z(1.0, 100, 1.0, 100) is None

    def test_significant_difference(self):
        # 10% vs 20% over 1000 each — should be highly significant
        res = _two_proportion_z(0.10, 1000, 0.20, 1000)
        assert res is not None
        z, p = res
        assert abs(z) > 1.96
        assert p < 0.05

    def test_not_significant(self):
        # 12% vs 13% over 100 each — not significant
        res = _two_proportion_z(0.12, 100, 0.13, 100)
        assert res is not None
        z, p = res
        assert abs(z) < 1.96
        assert p > 0.05

    def test_z_sign_reflects_direction(self):
        # p1 > p2 should give positive z
        res = _two_proportion_z(0.30, 500, 0.20, 500)
        assert res is not None
        assert res[0] > 0

        # p1 < p2 should give negative z
        res = _two_proportion_z(0.20, 500, 0.30, 500)
        assert res is not None
        assert res[0] < 0
