"""Rula brand design tokens for Streamlit UI — dark mode (Phase 2).

Primary purple #6B4C9A; deep navy-purple surfaces; semantic tier/audit colors
tuned for legibility on dark backgrounds (presentation only).
"""

from __future__ import annotations

# --- Brand (chrome, CTAs, links via Streamlit theme primaryColor) ---
PRIMARY = "#6B4C9A"
PRIMARY_HOVER = "#7D5EAE"

# --- Surfaces & text (match .streamlit/config.toml [theme]) ---
BACKGROUND = "#121018"
BACKGROUND_SECONDARY = "#1C1826"
TEXT = "#E8E4EF"
TEXT_MUTED = "#B8B0C8"
TEXT_LABEL = "#A89BC4"
BORDER = "#352E4A"

SIDEBAR_BACKGROUND = "#16121E"

# --- Semantic status — brighter fills for contrast on dark page chrome ---
TIER_COLORS: dict[str, str] = {
    "HIGH": "#10B981",
    "MEDIUM": "#F59E0B",
    "LOW": "#F87171",
}

AUDIT_COLORS: dict[str, str] = {
    "PASS": "#10B981",
    "REVIEW": "#F59E0B",
    "FAIL": "#F87171",
}

# Pending / unknown tier — readable on dark purple-gray background
NEUTRAL_MUTED = "#A89BC4"

# Risk chips: dark panel + light text (not light-mode pastels)
RISK_CHIP_BACKGROUND = "#3D2830"
RISK_CHIP_TEXT = "#FECDD3"

SOLID_BADGE_TEXT = "#FFFFFF"

# Subtle ring so pills separate from same-hue page background
PILL_OUTLINE = "rgba(255,255,255,0.12)"
