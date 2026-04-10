from __future__ import annotations

import os


def prospecting_disabled() -> bool:
    return os.environ.get("RULA_DISABLE_PROSPECTING", "").strip().lower() in ("1", "true", "yes")


def map_disabled() -> bool:
    return os.environ.get("RULA_DISABLE_MAP", "").strip().lower() in ("1", "true", "yes")
