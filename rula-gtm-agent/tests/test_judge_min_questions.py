from __future__ import annotations

from unittest.mock import patch

from src.agents.audit.judge import judge_prospecting
from src.schemas.account import Account, Contact, EnrichedAccount
from src.schemas.prospecting import OutreachEmail, ProspectingOutput, ValuePropMatch


def _minimal_output(questions: list[str]) -> ProspectingOutput:
    return ProspectingOutput(
        account_id=1,
        matched_value_props=[
            ValuePropMatch(value_prop="total_cost_of_care", score=90, reasoning="r"),
        ],
        email=OutreachEmail(subject_line="Acme", body="Acme body " * 20, cta="Yes?"),
        discovery_questions=questions,
        quality_score=4.0,
    )


def _ctx() -> tuple[Account, EnrichedAccount]:
    acc = Account(
        account_id=1,
        company="Acme Health",
        industry="Health system",
        us_employees=10000,
        contact=Contact(name="Pat", title="VP"),
        health_plan="Anthem",
    )
    enr = EnrichedAccount(account=acc, icp_fit_score=90, data_completeness_score=95, flags=[])
    return acc, enr


def test_judge_penalizes_below_min_questions_when_min_is_three() -> None:
    acc, enr = _ctx()
    out = _minimal_output(["Only one?"])
    with patch("src.agents.audit.judge.load_config") as m:
        m.return_value.min_discovery_questions = 3
        r = judge_prospecting(out, acc, enr)
    assert r.audit_score < 5.0
    assert any("3" in s for s in r.correction_suggestions)


def test_judge_accepts_two_questions_when_min_is_two() -> None:
    acc, enr = _ctx()
    out = _minimal_output(["First question?", "Second question?"])
    with patch("src.agents.audit.judge.load_config") as m:
        m.return_value.min_discovery_questions = 2
        r = judge_prospecting(out, acc, enr)
    assert not any("Provide at least" in s for s in r.correction_suggestions)
