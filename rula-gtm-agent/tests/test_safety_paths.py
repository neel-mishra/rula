"""Tests for filesystem-safe path helpers."""
from __future__ import annotations

import pytest

from src.safety.paths import assert_resolved_path_under_base, safe_handoff_filename_component


def test_safe_component_strips_traversal() -> None:
    assert ".." not in safe_handoff_filename_component("../evil")
    assert "/" not in safe_handoff_filename_component("a/b")
    assert "\\" not in safe_handoff_filename_component("a\\b")


def test_safe_component_fallback_for_empty() -> None:
    s = safe_handoff_filename_component("   ")
    assert s.startswith("id_")


def test_assert_under_base_accepts_child() -> None:
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        child = base / "ok.json"
        assert_resolved_path_under_base(child, base)


def test_assert_under_base_rejects_escape() -> None:
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        outside = base.parent / "outside.json"
        with pytest.raises(ValueError, match="outside base"):
            assert_resolved_path_under_base(outside, base)
