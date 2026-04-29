"""Adapter unit tests — EvalResult shape + empty-dataset path.

These tests do not hit the database. They exercise the pure result-
shaping helper directly and assert the adapter handles empty input
without raising.
"""

from __future__ import annotations

import uuid

import pytest

from core.gold_eval.adapter import (
    _build_eval_result,
    run_brief_gold,
    run_draft_gold,
    run_memory_gold,
    run_safety_gold,
    run_triage_gold,
)


def test_build_eval_result_perfect_pass():
    res = _build_eval_result(
        user_id=uuid.uuid4(), mailbox_id=uuid.uuid4(),
        eval_type="triage_gold", threshold=0.95,
        pass_count=10, fail_count=0, details=[],
    )
    assert res.pass_rate == 1.0
    assert res.passed is True
    assert res.eval_type == "triage_gold"


def test_build_eval_result_below_threshold():
    res = _build_eval_result(
        user_id=uuid.uuid4(), mailbox_id=uuid.uuid4(),
        eval_type="draft_quality_gold", threshold=0.99,
        pass_count=8, fail_count=2, details=[],
    )
    assert res.pass_rate == pytest.approx(0.8)
    assert res.passed is False


def test_build_eval_result_empty_total():
    res = _build_eval_result(
        user_id=uuid.uuid4(), mailbox_id=uuid.uuid4(),
        eval_type="safety_gold", threshold=0.99,
        pass_count=0, fail_count=0, details=[],
    )
    assert res.total_evaluated == 0
    assert res.passed is True


@pytest.mark.asyncio
async def test_run_triage_gold_empty_samples():
    res = await run_triage_gold(
        [], user_id=uuid.uuid4(), mailbox_id=uuid.uuid4(),
    )
    assert res.eval_type == "triage_gold"
    assert res.total_evaluated == 0


@pytest.mark.asyncio
async def test_run_draft_gold_empty_samples():
    res = await run_draft_gold(
        [], user_id=uuid.uuid4(), mailbox_id=uuid.uuid4(),
    )
    assert res.total_evaluated == 0


@pytest.mark.asyncio
async def test_run_brief_gold_empty_samples():
    res = await run_brief_gold(
        [], user_id=uuid.uuid4(), mailbox_id=uuid.uuid4(),
    )
    assert res.total_evaluated == 0


@pytest.mark.asyncio
async def test_run_memory_gold_empty_samples():
    res = await run_memory_gold(
        [], user_id=uuid.uuid4(), mailbox_id=uuid.uuid4(),
    )
    assert res.total_evaluated == 0


@pytest.mark.asyncio
async def test_run_safety_gold_empty_samples():
    res = await run_safety_gold(
        [], user_id=uuid.uuid4(), mailbox_id=uuid.uuid4(),
    )
    assert res.total_evaluated == 0
