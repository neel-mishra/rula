from __future__ import annotations

import html

import streamlit as st

from src.ui.theme import (
    AUDIT_COLORS,
    NEUTRAL_MUTED,
    PILL_OUTLINE,
    RISK_CHIP_BACKGROUND,
    RISK_CHIP_TEXT,
    SOLID_BADGE_TEXT,
    TIER_COLORS,
)


def _pill_style(bg: str) -> str:
    return (
        f"background:{bg};color:{SOLID_BADGE_TEXT};padding:4px 12px;"
        f"border-radius:12px;font-weight:600;font-size:14px;"
        f"box-shadow:0 0 0 1px {PILL_OUTLINE};"
    )


def _badge_style(bg: str) -> str:
    return (
        f"background:{bg};color:{SOLID_BADGE_TEXT};padding:3px 10px;"
        f"border-radius:10px;font-size:13px;font-weight:600;"
        f"box-shadow:0 0 0 1px {PILL_OUTLINE};"
    )


def confidence_pill(tier: str, score: int | float | None = None) -> str:
    color = TIER_COLORS.get(tier, NEUTRAL_MUTED)
    tier_e = html.escape(str(tier), quote=True)
    if score is None:
        label = tier_e
    else:
        label = f"{tier_e} ({html.escape(str(score), quote=True)})"
    return f'<span style="{_pill_style(color)}">{label}</span>'


def audit_badge(passed: bool | None) -> str:
    if passed is None:
        label, color = "Pending", NEUTRAL_MUTED
    elif passed:
        label, color = "Ready to Send", AUDIT_COLORS["PASS"]
    else:
        label, color = "Needs Review", AUDIT_COLORS["REVIEW"]
    return f'<span style="{_badge_style(color)}">{label}</span>'


def risk_chips(risks: list[str]) -> str:
    if not risks:
        return ""
    chips = " &nbsp; ".join(
        f'<span style="background:{RISK_CHIP_BACKGROUND};color:{RISK_CHIP_TEXT};padding:2px 8px;'
        f'border-radius:8px;font-size:12px;box-shadow:0 0 0 1px {PILL_OUTLINE};">'
        f"{html.escape(str(r), quote=True)}</span>"
        for r in risks
    )
    return chips


def render_empty_state(message: str = "No results yet. Run a pipeline to see output.") -> None:
    st.info(message)


def render_error(error: Exception | str, recovery: str = "") -> None:
    msg = str(error)
    if recovery:
        msg += f"\n\n**Suggested action**: {recovery}"
    st.error(msg)


def render_permission_error(error: PermissionError) -> None:
    st.error(f"Access denied: {error}")
    st.caption("Switch to a role with the required permissions using the sidebar selector.")


def render_runtime_error(error: RuntimeError) -> None:
    msg = str(error)
    if "circuit breaker" in msg.lower():
        st.warning("System temporarily unavailable due to repeated errors. Please try again shortly.")
    elif "disabled" in msg.lower():
        st.warning("This pipeline has been disabled by an administrator. Contact your team lead.")
    else:
        st.error(msg)


def copyable_block(label: str, text: str) -> None:
    st.markdown(f"**{label}**")
    st.code(text, language=None)
