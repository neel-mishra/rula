from __future__ import annotations

from src.explainability.economics import estimate_economics
from src.explainability.threshold import explain_threshold, explain_tier_assignment
from src.explainability.value_prop import explain_value_prop
from src.schemas.account import Account, Contact, EnrichedAccount
from src.schemas.prospecting import ValuePropMatch


def test_explain_threshold_high() -> None:
    result = explain_threshold("HIGH", 85, [])
    assert "High confidence" in result
    assert "85" in result


def test_explain_tier_assignment_medium_with_risks() -> None:
    reasons = explain_tier_assignment(55, ["SECONDHAND_SOURCE", "SECONDHAND_HIGH_ALERT"])
    assert any("MEDIUM" in r for r in reasons)
    assert any("secondhand" in r.lower() for r in reasons)


def test_economics_basic() -> None:
    econ = estimate_economics(10000)
    assert econ.eligible_lives == 8500
    assert econ.annual_contract_value > 0
    assert "10,000" in econ.rationale


def test_economics_campaign_multiplier() -> None:
    base = estimate_economics(10000, campaign_types=["launch_email"])
    toolkit = estimate_economics(10000, campaign_types=["manager_toolkit"])
    assert toolkit.annual_contract_value > base.annual_contract_value


def test_explain_value_prop_health() -> None:
    account = Account(
        account_id=1, company="Test Health", industry="Health system",
        us_employees=5000, contact=Contact(name="X", title="Y"),
        health_plan="Anthem", notes="high turnover",
    )
    enriched = EnrichedAccount(account=account, icp_fit_score=80, data_completeness_score=90, flags=[])
    vpm = ValuePropMatch(value_prop="total_cost_of_care", score=80, reasoning="test")
    explanation = explain_value_prop(vpm, enriched)
    assert "cost" in explanation.lower()
    assert "health system" in explanation.lower()
