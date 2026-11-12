"""Diagram themes: built-ins shipped as JSON, plus customization overrides."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field, replace
from importlib import resources
from typing import Any

from md2xarticle.errors import UsageError

BUILTIN_THEMES = ("mono", "soft", "warm", "x-light", "x-dark")
DEFAULT_THEME = "mono"
HAND_DRAWN_SEED = 1
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    if not _HEX.match(value):
        raise UsageError(f"not a #RRGGBB color: {value!r}")
    v = value.lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


@dataclass(frozen=True)
class Theme:
    name: str
    canvas: str
    title_color: str
    subtitle_color: str | None = None  # cover subtitle; None uses title_color
    corner_radius: int = 8
    edge_width: float = 2.0
    margin: float = 0.06
    max_scale: float = 3.0
    mermaid_theme: str = "base"
    theme_variables: dict[str, Any] = field(default_factory=dict)
    flowchart: dict[str, Any] = field(default_factory=dict)
    sequence: dict[str, Any] = field(default_factory=dict)
    git_graph: dict[str, Any] = field(default_factory=dict)

    def theme_css(self) -> str:
        r = self.corner_radius
        w = self.edge_width
        return (
            f".node rect, .node circle, .node polygon, .node path "
            f"{{ rx: {r}; ry: {r}; stroke-width: 2px; }} "
            f".edgePath .path, .flowchart-link {{ stroke-width: {w:g}px; }} "
            f".cluster rect {{ rx: {r + 4}; ry: {r + 4}; stroke-width: 1.5px; }} "
            f".edgeLabel {{ font-size: 13px; }}"
        )

    def mermaid_config(self) -> dict[str, Any]:
        """Config passed to Mermaid. Copies, so callers cannot mutate the theme."""
        return {
            "themeVariables": copy.deepcopy(self.theme_variables),
            "flowchart": copy.deepcopy(self.flowchart),
            "sequence": copy.deepcopy(self.sequence),
            "gitGraph": copy.deepcopy(self.git_graph),
            "themeCSS": self.theme_css(),
            # Mermaid draws some shapes (stadium, cylinder, ...) with rough.js,
            # which is seeded randomly unless this is set. A fixed seed keeps
            # PNG output byte-identical across runs.
            "handDrawnSeed": HAND_DRAWN_SEED,
        }

    def with_overrides(self, **changes: Any) -> "Theme":
        return replace(self, **changes)


def load_builtin(name: str) -> Theme:
    if name not in BUILTIN_THEMES:
        raise UsageError(
            f"unknown theme {name!r}; built-in themes: {', '.join(BUILTIN_THEMES)}"
        )
    raw = resources.files("md2xarticle.themes").joinpath(f"{name}.json").read_text(
        encoding="utf-8"
    )
    data = json.loads(raw)
    theme = Theme(**data)
    hex_to_rgb(theme.canvas)
    hex_to_rgb(theme.title_color)
    if theme.subtitle_color is not None:
        hex_to_rgb(theme.subtitle_color)
    return theme
