from __future__ import annotations


def flag_actions(tier: str, risks: list[str]) -> list[str]:
    if tier == "HIGH":
        actions = [
            "Approve MAP with standard verification",
            "Schedule campaign calendar confirmation",
        ]
        try:
            from src.context.business_context import BusinessContextRegistry
            reg = BusinessContextRegistry.get()
            if reg.bundle.loaded and reg.bundle.icp.expansion_indicators:
                actions.append("Check for expansion signals: " + reg.bundle.icp.expansion_indicators[0])
        except Exception:
            pass
        return actions
    if tier == "MEDIUM":
        actions = ["Conditional approval pending first-party confirmation"]
        if "SECONDHAND_SOURCE" in risks:
            actions.append("Request written confirmation from decision-maker")
        try:
            from src.context.business_context import BusinessContextRegistry
            reg = BusinessContextRegistry.get()
            if reg.bundle.loaded and reg.bundle.icp.contraction_indicators:
                actions.append("Watch for contraction signals: " + reg.bundle.icp.contraction_indicators[0])
        except Exception:
            pass
        return actions
    return [
        "Do not count MAP toward quota",
        "Collect direct evidence with campaign specifics and timeline",
    ]
