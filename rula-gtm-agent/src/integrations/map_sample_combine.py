"""MAP demo: combine two sample evidence rows (GAP-M3)."""

from __future__ import annotations

from typing import Any


def combine_first_two_map_evidence(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Concatenate the first two JSON evidence fixtures with a stable separator."""
    if len(items) < 2:
        raise ValueError("Need at least two evidence items to combine.")
    a, b = items[0], items[1]
    eid_a = str(a.get("evidence_id", ""))
    eid_b = str(b.get("evidence_id", ""))
    text_a = str(a.get("text", ""))
    text_b = str(b.get("text", ""))
    return {
        "evidence_id": f"{eid_a}+{eid_b}",
        "text": text_a + "\n\n---\n\n" + text_b,
    }
