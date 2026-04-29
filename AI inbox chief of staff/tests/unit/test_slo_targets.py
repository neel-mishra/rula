"""Unit tests for SLO target evaluation + percentile math."""

from __future__ import annotations

import pytest

from core.slo.metrics import _percentile
from core.slo.targets import (
    MetricCategory,
    MetricStatus,
    MetricTarget,
    Operator,
    TARGETS,
    evaluate,
)


class TestEvaluate:
    def test_le_pass(self):
        t = MetricTarget("x", "x", MetricCategory.QUALITY, 0.01, Operator.LE, "rate", "")
        assert evaluate(0.005, t) is MetricStatus.PASS
        assert evaluate(0.01, t) is MetricStatus.PASS

    def test_le_warn_inside_20pct_band(self):
        t = MetricTarget("x", "x", MetricCategory.QUALITY, 0.01, Operator.LE, "rate", "")
        # target=0.01, band=0.002, warn range (0.01, 0.012]
        assert evaluate(0.011, t) is MetricStatus.WARN
        assert evaluate(0.012, t) is MetricStatus.WARN

    def test_le_fail_past_band(self):
        t = MetricTarget("x", "x", MetricCategory.QUALITY, 0.01, Operator.LE, "rate", "")
        assert evaluate(0.015, t) is MetricStatus.FAIL

    def test_ge_pass(self):
        t = MetricTarget("x", "x", MetricCategory.QUALITY, 0.99, Operator.GE, "rate", "")
        assert evaluate(0.99, t) is MetricStatus.PASS
        assert evaluate(1.0, t) is MetricStatus.PASS

    def test_ge_warn_inside_band(self):
        t = MetricTarget("x", "x", MetricCategory.QUALITY, 0.50, Operator.GE, "rate", "")
        # target=0.5, band=0.1, warn range [0.4, 0.5)
        assert evaluate(0.45, t) is MetricStatus.WARN
        assert evaluate(0.40, t) is MetricStatus.WARN

    def test_ge_fail_below_band(self):
        t = MetricTarget("x", "x", MetricCategory.QUALITY, 0.50, Operator.GE, "rate", "")
        assert evaluate(0.30, t) is MetricStatus.FAIL

    def test_none_is_not_measured(self):
        t = MetricTarget("x", "x", MetricCategory.QUALITY, 0.01, Operator.LE, "rate", "")
        assert evaluate(None, t) is MetricStatus.NOT_MEASURED


class TestTargetRegistry:
    def test_all_expected_targets_registered(self):
        expected = {
            "false_archive_rate",
            "false_brief_rate",
            "draft_grounding_failure_rate",
            "ingest_to_triage_p95",
            "ingest_to_triage_p99",
            "draft_generation_p95",
            "brief_completion_rate",
            "brief_timeliness_rate",
            "undo_success_rate",
            "undo_execution_p95",
            "prompt_injection_pass_rate",
            "llm_cache_hit_rate",
            "cost_per_inbox_per_day",
        }
        assert expected <= set(TARGETS.keys())

    def test_ids_match_keys(self):
        for key, target in TARGETS.items():
            assert target.id == key

    def test_rate_targets_in_unit_range(self):
        for t in TARGETS.values():
            if t.unit == "rate":
                assert 0.0 <= t.target_value <= 1.0


class TestPercentile:
    def test_empty(self):
        assert _percentile([], 95) is None

    def test_single_value(self):
        assert _percentile([5.0], 95) == 5.0

    def test_median_of_odd(self):
        assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == pytest.approx(3.0)

    def test_p95_of_known(self):
        values = [float(i) for i in range(1, 101)]  # 1..100
        v = _percentile(values, 95)
        assert v is not None
        assert 95.0 <= v <= 96.0

    def test_p99_of_known(self):
        values = [float(i) for i in range(1, 101)]
        v = _percentile(values, 99)
        assert v is not None
        assert 99.0 <= v <= 100.0

    def test_unsorted_input_ok(self):
        values = [5.0, 1.0, 3.0, 4.0, 2.0]
        assert _percentile(values, 50) == pytest.approx(3.0)
