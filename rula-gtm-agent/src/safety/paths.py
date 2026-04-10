"""Filesystem-safe path helpers for handoff and archive writes."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_MAX_COMPONENT_LEN = 120
_SAFE_COMPONENT_FULL = re.compile(r"^[A-Za-z0-9._+-]+$")


def safe_handoff_filename_component(raw: str, *, max_len: int = _MAX_COMPONENT_LEN) -> str:
    """Return a filename-safe component derived from *raw* (no path separators).

    Preserves readable IDs when they are already safe; otherwise falls back to a
    stable hashed prefix so writes cannot escape via ``..`` or slashes.
    """
    s = (raw or "").strip()
    if not s:
        return _fallback_slug(raw)

    # Normalize obvious traversal / path separators early
    normalized = s.replace("\\", "_").replace("/", "_").strip()
    if not normalized or normalized in (".", ".."):
        return _fallback_slug(raw)

    cleaned = re.sub(r"[^A-Za-z0-9._+-]", "_", normalized)
    cleaned = cleaned.strip("._")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    if not cleaned or cleaned in (".", ".."):
        return _fallback_slug(raw)

    if len(cleaned) > max_len:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        cleaned = f"{cleaned[: max_len - 17]}_{digest}"

    if not _SAFE_COMPONENT_FULL.match(cleaned):
        return _fallback_slug(raw)
    return cleaned


def _fallback_slug(raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"id_{digest}"


def assert_resolved_path_under_base(path: Path, base: Path) -> None:
    """Raise ValueError if *path* is not under *base* after resolution."""
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError as e:
        raise ValueError(f"Refusing to write outside base directory: {path} not under {base}") from e
