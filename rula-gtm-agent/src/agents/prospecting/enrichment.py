from __future__ import annotations

from src.schemas.account import Account, EnrichedAccount


def enrich_account(account: Account) -> EnrichedAccount:
    flags: list[str] = []
    completeness = 100

    if not account.contact.name:
        flags.append("NEEDS_CONTACT_RESEARCH")
        completeness -= 30
    if not account.health_plan or account.health_plan.lower() == "unknown":
        flags.append("UNKNOWN_HEALTH_PLAN")
        completeness -= 15
    if account.us_employees < 3000:
        flags.append("BELOW_ICP_THRESHOLD")
    if "field-based" in account.notes.lower():
        flags.append("LIMITED_DIGITAL_ACCESS")

    icp = 20
    industry = account.industry.lower()
    if "health" in industry or "university" in industry:
        icp += 40
    if account.us_employees >= 3000:
        icp += 20
    if (account.health_plan or "").lower() in {"anthem", "aetna", "cigna"}:
        icp += 20

    return EnrichedAccount(
        account=account,
        icp_fit_score=min(100, icp),
        data_completeness_score=max(0, completeness),
        flags=flags,
    )
