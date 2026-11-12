"""Find the font for cover titles. Prefers the DejaVu Sans that mermaidx bundles,
so cover text matches diagram text on every machine."""

from __future__ import annotations

import importlib.util
from pathlib import Path

TITLE_FONT_FILES = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf")


def title_font_path(extra_dirs: list[Path]) -> Path | None:
    dirs: list[Path] = []
    spec = importlib.util.find_spec("mermaidx")
    if spec is not None and spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            dirs.append(Path(loc) / "assets" / "fonts")
    dirs.extend(extra_dirs)
    for name in TITLE_FONT_FILES:
        for d in dirs:
            p = d / name
            if p.is_file():
                return p
    return None
