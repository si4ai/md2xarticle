"""Load a ``--custom-path`` TOML file into a validated ``Customization``.

Schema (every key optional)::

    theme = "soft"            # built-in base theme
    size = "1600x900"         # body images, must be 16:9
    cover_size = "1500x600"   # cover, must be 5:2
    cover = "diagram:2"       # "diagram:N" or "title" (title only)
    cover_title = "Title"     # "" turns the title off

    [style]
    corner_radius = 8         # px, node corner radius
    spacing = 24              # px, padding inside flowchart nodes
    node_spacing = 60         # px, between nodes in a rank
    rank_spacing = 70         # px, between ranks
    edge_width = 2.0          # px
    margin = 0.06             # fraction of each canvas side, 0.04 to 0.25

    [palette]                 # #RRGGBB colors
    canvas = "#FFFFFF"
    title = "#111111"
    primary = "#D9EEF2"
    primary_border = "#2F8A8A"
    primary_text = "#163239"
    secondary = "#E4EEF8"
    tertiary = "#E8F4EA"
    line = "#5A7380"
    text = "#1A2A30"

    [theme_variables]         # raw Mermaid themeVariables, applied last

    [[diagrams]]              # per-diagram overrides, by 1-based index
    id = 1
    layout = "LR"             # TD, TB, BT, RL, or LR (flowchart and graph only)
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from md2xarticle.errors import UsageError
from md2xarticle.theme import BUILTIN_THEMES, Theme, hex_to_rgb, load_builtin

LAYOUTS = ("TD", "TB", "BT", "RL", "LR")

_TOP_KEYS = {
    "theme",
    "size",
    "cover_size",
    "cover",
    "cover_title",
    "style",
    "palette",
    "theme_variables",
    "diagrams",
}
_STYLE_KEYS = {"corner_radius", "spacing", "node_spacing", "rank_spacing", "edge_width", "margin"}
_PALETTE_TO_VARS = {
    "primary": ("primaryColor", "mainBkg", "actorBkg"),
    "primary_border": ("primaryBorderColor", "nodeBorder", "actorBorder"),
    "primary_text": ("primaryTextColor", "actorTextColor"),
    "secondary": ("secondaryColor",),
    "tertiary": ("tertiaryColor",),
    "line": ("lineColor",),
    "text": ("textColor", "titleColor"),
}
_PALETTE_KEYS = set(_PALETTE_TO_VARS) | {"canvas", "title"}
_DIAGRAM_KEYS = {"id", "layout"}


@dataclass(frozen=True)
class DiagramOverride:
    layout: str | None = None


@dataclass(frozen=True)
class Customization:
    theme_name: str | None = None
    size: tuple[int, int] | None = None
    cover_size: tuple[int, int] | None = None
    cover_diagram: int | None = None
    cover_title_only: bool = False
    cover_title: str | None = None
    style: dict[str, Any] = field(default_factory=dict)
    palette: dict[str, str] = field(default_factory=dict)
    theme_variables: dict[str, Any] = field(default_factory=dict)
    diagrams: dict[int, DiagramOverride] = field(default_factory=dict)

    def build_theme(self, fallback_name: str) -> Theme:
        """The base theme (file wins over ``fallback_name``) with overrides applied."""
        theme = load_builtin(self.theme_name or fallback_name)
        tv = dict(theme.theme_variables)
        flow = dict(theme.flowchart)
        changes: dict[str, Any] = {}
        for key, names in _PALETTE_TO_VARS.items():
            if key in self.palette:
                for name in names:
                    tv[name] = self.palette[key]
        if "canvas" in self.palette:
            changes["canvas"] = self.palette["canvas"]
        if "title" in self.palette:
            changes["title_color"] = self.palette["title"]
        tv.update(self.theme_variables)
        s = self.style
        if "corner_radius" in s:
            changes["corner_radius"] = s["corner_radius"]
        if "edge_width" in s:
            changes["edge_width"] = float(s["edge_width"])
        if "margin" in s:
            changes["margin"] = float(s["margin"])
        if "spacing" in s:
            flow["padding"] = s["spacing"]
        if "node_spacing" in s:
            flow["nodeSpacing"] = s["node_spacing"]
        if "rank_spacing" in s:
            flow["rankSpacing"] = s["rank_spacing"]
        return theme.with_overrides(theme_variables=tv, flowchart=flow, **changes)


def parse_size(text: str, ratio: tuple[int, int], what: str) -> tuple[int, int]:
    """Parse ``WxH`` and require the exact ratio, for example 16:9."""
    try:
        w_s, h_s = text.lower().split("x")
        w, h = int(w_s), int(h_s)
    except (ValueError, AttributeError):
        raise UsageError(f"{what} must look like WxH, got {text!r}") from None
    if w <= 0 or h <= 0:
        raise UsageError(f"{what} must be positive, got {text!r}")
    rw, rh = ratio
    if w * rh != h * rw:
        raise UsageError(f"{what} must be {rw}:{rh} for now, got {text!r}")
    return w, h


def _unknown(keys: set[str], allowed: set[str], where: str) -> None:
    extra = sorted(keys - allowed)
    if extra:
        raise UsageError(f"unknown key(s) in {where}: {', '.join(extra)}")


def _int_range(value: Any, lo: int, hi: int, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise UsageError(f"{where} must be an integer from {lo} to {hi}, got {value!r}")
    return value


def _num_range(value: Any, lo: float, hi: float, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise UsageError(f"{where} must be a number from {lo} to {hi}, got {value!r}")
    return float(value)


def from_dict(data: dict[str, Any], where: str = "customization") -> Customization:
    _unknown(set(data), _TOP_KEYS, where)
    kw: dict[str, Any] = {}

    if "theme" in data:
        if data["theme"] not in BUILTIN_THEMES:
            raise UsageError(
                f"{where}: unknown theme {data['theme']!r}; built-in themes: "
                f"{', '.join(BUILTIN_THEMES)}"
            )
        kw["theme_name"] = data["theme"]
    if "size" in data:
        kw["size"] = parse_size(str(data["size"]), (16, 9), f"{where}: size")
    if "cover_size" in data:
        kw["cover_size"] = parse_size(str(data["cover_size"]), (5, 2), f"{where}: cover_size")
    if "cover" in data:
        cover = data["cover"]
        if cover == "title":
            kw["cover_title_only"] = True
        elif isinstance(cover, str) and cover.startswith("diagram:"):
            try:
                kw["cover_diagram"] = int(cover.split(":", 1)[1])
            except ValueError:
                raise UsageError(f"{where}: cover must be 'diagram:N' or 'title'") from None
            if kw["cover_diagram"] < 1:
                raise UsageError(f"{where}: cover diagram index starts at 1")
        else:
            raise UsageError(f"{where}: cover must be 'diagram:N' or 'title', got {cover!r}")
    if "cover_title" in data:
        if not isinstance(data["cover_title"], str):
            raise UsageError(f"{where}: cover_title must be a string")
        kw["cover_title"] = data["cover_title"]

    style = data.get("style", {})
    if not isinstance(style, dict):
        raise UsageError(f"{where}: [style] must be a table")
    _unknown(set(style), _STYLE_KEYS, f"{where} [style]")
    checked: dict[str, Any] = {}
    for key in ("corner_radius", "spacing", "node_spacing", "rank_spacing"):
        if key in style:
            checked[key] = _int_range(style[key], 0, 400, f"{where} [style] {key}")
    if "edge_width" in style:
        checked["edge_width"] = _num_range(style["edge_width"], 0.5, 12, f"{where} [style] edge_width")
    if "margin" in style:
        checked["margin"] = _num_range(style["margin"], 0.04, 0.25, f"{where} [style] margin")
    kw["style"] = checked

    palette = data.get("palette", {})
    if not isinstance(palette, dict):
        raise UsageError(f"{where}: [palette] must be a table")
    _unknown(set(palette), _PALETTE_KEYS, f"{where} [palette]")
    for key, value in palette.items():
        try:
            hex_to_rgb(str(value))
        except UsageError:
            raise UsageError(f"{where} [palette] {key} must be #RRGGBB, got {value!r}") from None
    kw["palette"] = dict(palette)

    tv = data.get("theme_variables", {})
    if not isinstance(tv, dict):
        raise UsageError(f"{where}: [theme_variables] must be a table")
    kw["theme_variables"] = dict(tv)

    diagrams: dict[int, DiagramOverride] = {}
    for i, entry in enumerate(data.get("diagrams", []), start=1):
        if not isinstance(entry, dict):
            raise UsageError(f"{where}: [[diagrams]] entry {i} must be a table")
        _unknown(set(entry), _DIAGRAM_KEYS, f"{where} [[diagrams]] entry {i}")
        if "id" not in entry:
            raise UsageError(f"{where}: [[diagrams]] entry {i} needs id = N (1-based)")
        idx = _int_range(entry["id"], 1, 10_000, f"{where} [[diagrams]] id")
        layout = entry.get("layout")
        if layout is not None and layout not in LAYOUTS:
            raise UsageError(
                f"{where}: [[diagrams]] id {idx} layout must be one of {', '.join(LAYOUTS)}"
            )
        diagrams[idx] = DiagramOverride(layout=layout)
    kw["diagrams"] = diagrams
    return Customization(**kw)


def load(path: Path) -> Customization:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise UsageError(f"customization file not found: {path}") from None
    except OSError as exc:
        raise UsageError(f"cannot read customization file {path}: {exc.strerror}") from None
    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"{path.name}: invalid TOML: {exc}") from None
    return from_dict(data, where=path.name)
