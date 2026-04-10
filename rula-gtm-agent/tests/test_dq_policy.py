from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.prospecting.dq_policy import evaluate_dq_policy
from src.orchestrator.graph import run_prospecting
from src.schemas.account import Account, Contact, EnrichedAccount


def _enriched(flags: list[str]) -> EnrichedAccount:
    acc = Account(
        account_id=1,
        company="Co",
        industry="Health system",
        us_employees=5000,
        contact=Contact(name="A", title="B"),
        health_plan="Anthem",
    )
    return EnrichedAccount(
        account=acc,
        icp_fit_score=80,
        data_completeness_score=90,
        flags=flags,
    )


def test_evaluate_blocks_matching_rule(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    policy = tmp_path / "dq.yaml"
    policy.write_text(Path("tests/fixtures/dq_policy.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("RULA_DQ_POLICY_PATH", str(policy))
    ev = evaluate_dq_policy(_enriched(["BELOW_ICP_THRESHOLD"]))
    assert ev.action == "block_generation"
    assert ev.matched_rule_id == "block_below_icp"


def test_pipeline_skips_small_college(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    policy = tmp_path / "dq.yaml"
    policy.write_text(Path("tests/fixtures/dq_policy.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("RULA_DQ_POLICY_PATH", str(policy))
    payload = {
        "account_id": 6,
        "company": "Great Plains Community College",
        "industry": "Education",
        "us_employees": 1800,
        "contact": {"name": "Tom Bradley", "title": "HR Director"},
        "health_plan": "State employee plan",
        "notes": "Small community college; limited benefits budget",
    }
    out = run_prospecting(payload, actor_role="user")
    assert out.skipped is True
    assert "block_below_icp" in out.skip_reasons or out.skip_reasons
