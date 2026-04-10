from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.safety.atomic_io import atomic_write_json, atomic_write_text


def test_atomic_write_json_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "a.json"
    atomic_write_json(p, {"x": 1, "y": [2, 3]})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"x": 1, "y": [2, 3]}


def test_atomic_write_text_leaves_no_tmp_suffix_files(tmp_path: Path) -> None:
    p = tmp_path / "out.txt"
    atomic_write_text(p, "complete")
    assert p.read_text(encoding="utf-8") == "complete"
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_write_json_rejects_path_outside_base(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.json"
    with pytest.raises(ValueError, match="outside base"):
        atomic_write_json(outside, {"a": 1}, base_dir=base)
