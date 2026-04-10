"""Landing page ↔ Streamlit query-string helpers (unit-testable; no Streamlit runtime import).

The Vercel landing app opens the Streamlit app with ``?role=`` and ``?page=`` query
parameters. Values may be strings or single-element lists depending on runtime.
"""

from __future__ import annotations

# Separator for fingerprint tuple (page, role); not used in URLs.
FP_SEP = "\x1e"


def normalize_query_value(value: object) -> str:
    """Return a stripped, lowercased scalar string for a query param value.

    Handles ``None``, ``str``, and single-element ``list`` / iterable shapes.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        return normalize_query_value(value[0])
    s = str(value).strip()
    return s.lower() if s else ""


def qp_scalar_get(qp: object, key: str) -> str:
    """Read ``key`` from a Streamlit ``query_params``-like mapping; never raises."""
    if qp is None:
        return ""
    try:
        raw = qp.get(key)  # type: ignore[union-attr]
    except Exception:
        return ""
    return normalize_query_value(raw)


def fingerprint(page_raw: str, role_raw: str) -> str:
    """Stable fingerprint for ``(page, role)`` query pair (may be partially empty)."""
    return f"{page_raw}{FP_SEP}{role_raw}"
