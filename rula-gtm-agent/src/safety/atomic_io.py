"""Atomic filesystem writes for connector artifacts (temp + replace)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.safety.paths import assert_resolved_path_under_base


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write *text* to *path* atomically: full content appears only after rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = path.resolve()
    parent = resolved.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{resolved.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
        os.replace(tmp_path, resolved)
    except BaseException:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(
    path: Path,
    data: Any,
    *,
    base_dir: Path | None = None,
    indent: int = 2,
) -> None:
    """JSON-encode *data* and write atomically. Optional *base_dir* containment check."""
    if base_dir is not None:
        assert_resolved_path_under_base(path, base_dir)
    text = json.dumps(data, indent=indent, default=str)
    atomic_write_text(path, text, encoding="utf-8")
