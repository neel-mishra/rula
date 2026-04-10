from __future__ import annotations

import html
import streamlit as st

TIER_COLORS = {"HIGH": "#10B981", "MEDIUM": "#F59E0B", "LOW": "#EF4444"}
AUDIT_COLORS = {"PASS": "#10B981", "REVIEW": "#F59E0B", "FAIL": "#EF4444"}


def confidence_pill(tier: str, score: int | float | None = None) -> str:
    color = TIER_COLORS.get(tier, "#6B7280")
    tier_e = html.escape(str(tier), quote=True)
    if score is None:
        label = tier_e
    else:
        label = f"{tier_e} ({html.escape(str(score), quote=True)})"
    return (
        f'<span style="background:{color};color:#fff;padding:4px 12px;'
        f'border-radius:12px;font-weight:600;font-size:14px;">{label}</span>'
    )


def audit_badge(passed: bool | None) -> str:
    if passed is None:
        label, color = "Pending", "#6B7280"
    elif passed:
        label, color = "Ready to Send", AUDIT_COLORS["PASS"]
    else:
        label, color = "Needs Review", AUDIT_COLORS["REVIEW"]
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:10px;font-size:13px;font-weight:600;">{label}</span>'
    )


def risk_chips(risks: list[str]) -> str:
    if not risks:
        return ""
    chips = " &nbsp; ".join(
        f'<span style="background:#FEE2E2;color:#991B1B;padding:2px 8px;'
        f'border-radius:8px;font-size:12px;">{html.escape(str(r), quote=True)}</span>'
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
