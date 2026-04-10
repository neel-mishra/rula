from __future__ import annotations

import pytest

from src.integrations.map_sample_combine import combine_first_two_map_evidence


def test_combine_joins_ids_and_separator() -> None:
    items = [
        {"evidence_id": "E1", "text": "alpha"},
        {"evidence_id": "E2", "text": "beta"},
    ]
    out = combine_first_two_map_evidence(items)
    assert out["evidence_id"] == "E1+E2"
    assert "\n\n---\n\n" in out["text"]
    assert "alpha" in out["text"] and "beta" in out["text"]


def test_combine_requires_two_rows() -> None:
    with pytest.raises(ValueError, match="at least two"):
        combine_first_two_map_evidence([{"evidence_id": "x", "text": "y"}])
