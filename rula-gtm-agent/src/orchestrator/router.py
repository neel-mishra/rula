from __future__ import annotations


def route_task(payload: dict) -> str:
    if "evidence_text" in payload:
        return "map_verification"
    return "prospecting"
