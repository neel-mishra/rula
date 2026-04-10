"""Tests for landing page query-string normalization (no Streamlit)."""

from __future__ import annotations

import pytest

from src.landing_bridge import FP_SEP, fingerprint, normalize_query_value, qp_scalar_get


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  MAP ", "map"),
        (["prospecting"], "prospecting"),
        ([], ""),
        (["Admin", "user"], "admin"),
    ],
)
def test_normalize_query_value(value: object, expected: str) -> None:
    assert normalize_query_value(value) == expected


def test_qp_scalar_get_dict() -> None:
    qp = {"page": "map", "role": ["viewer"]}
    assert qp_scalar_get(qp, "page") == "map"
    assert qp_scalar_get(qp, "role") == "viewer"
    assert qp_scalar_get(qp, "missing") == ""


def test_qp_scalar_get_bad_mapping() -> None:
    class Bad:
        def get(self, _key: str) -> None:
            raise RuntimeError("boom")

    assert qp_scalar_get(Bad(), "x") == ""


def test_fingerprint_roundtrip() -> None:
    assert fingerprint("map", "admin") == f"map{FP_SEP}admin"
    assert fingerprint("", "") == f"{FP_SEP}"
