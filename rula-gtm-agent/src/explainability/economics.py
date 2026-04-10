from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EconEstimate:
    employees: int
    eligible_lives: int
    estimated_utilization_rate: float
    monthly_pmpm: float
    annual_contract_value: float
    campaign_productivity_ratio: float
    rationale: str


DEFAULT_PMPM = 4.50
DEFAULT_UTILIZATION = 0.08
CAMPAIGN_MULTIPLIERS = {
    "launch_email": 1.2,
    "benefits_insert": 1.0,
    "manager_toolkit": 1.4,
}


def estimate_economics(
    us_employees: int,
    campaign_types: list[str] | None = None,
    eligible_pct: float = 0.85,
    utilization_override: float | None = None,
    pmpm_override: float | None = None,
) -> EconEstimate:
    eligible = int(us_employees * eligible_pct)
    utilization = utilization_override or DEFAULT_UTILIZATION
    pmpm = pmpm_override or DEFAULT_PMPM
    annual = eligible * pmpm * 12

    campaigns = campaign_types or ["launch_email"]
    multiplier = max(CAMPAIGN_MULTIPLIERS.get(c, 1.0) for c in campaigns)
    adjusted = annual * multiplier
    ratio = multiplier

    rationale = (
        f"With {us_employees:,} US employees, ~{eligible:,} eligible lives at "
        f"{eligible_pct:.0%} eligibility. At ${pmpm:.2f} PMPM and {utilization:.0%} "
        f"utilization, base ACV is ${annual:,.0f}. Campaign type(s) "
        f"[{', '.join(campaigns)}] apply a {ratio:.1f}x productivity multiplier, "
        f"yielding an adjusted ACV of ${adjusted:,.0f}."
    )

    return EconEstimate(
        employees=us_employees,
        eligible_lives=eligible,
        estimated_utilization_rate=utilization,
        monthly_pmpm=pmpm,
        annual_contract_value=adjusted,
        campaign_productivity_ratio=ratio,
        rationale=rationale,
    )
