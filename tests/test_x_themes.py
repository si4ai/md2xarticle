"""x-light and x-dark: X's palette, with X blue as a sparing accent."""

from __future__ import annotations

import json

import pytest

from md2xarticle import factory
from md2xarticle.customize import from_dict
from md2xarticle.errors import UsageError
from md2xarticle.theme import BUILTIN_THEMES, load_builtin
from tests.helpers import assert_canvas, fake_rendered

BLUE = "#1D9BF0"
PALETTES = {
    "x-light": {"canvas": "#FFFFFF", "text": "#0F1419", "secondary": "#536471", "border": "#CFD9DE", "fill": "#F7F9F9"},
    "x-dark": {"canvas": "#000000", "text": "#E7E9EA", "secondary": "#71767B", "border": "#2F3336", "fill": "#16181C"},
}


@pytest.mark.parametrize("name", sorted(PALETTES))
def test_palette_matches_x(name):
    p = PALETTES[name]
    theme = load_builtin(name)
    tv = theme.mermaid_config()["themeVariables"]
    assert theme.canvas == p["canvas"] == tv["background"]
    assert theme.title_color == p["text"] == tv["primaryTextColor"] == tv["textColor"]
    assert theme.subtitle_color == p["secondary"]
    assert tv["primaryBorderColor"] == tv["nodeBorder"] == tv["clusterBorder"] == p["border"]
    assert tv["primaryColor"] == tv["mainBkg"] == p["fill"]
    assert tv["darkMode"] is (name == "x-dark")


@pytest.mark.parametrize("name", sorted(PALETTES))
def test_blue_is_only_an_accent(name):
    tv = load_builtin(name).mermaid_config()["themeVariables"]
    assert tv["git0"] == BLUE  # gitGraph main branch
    accented = sorted(k for k, v in tv.items() if v == BLUE)
    assert accented == ["git0", "pie1", "tagLabelBackground", "tagLabelBorder"]


@pytest.mark.parametrize("name", sorted(PALETTES))
def test_cover_draws_subtitle_in_secondary_text(name):
    theme = load_builtin(name)
    cover = factory.COVER_COMPOSERS["cover"](theme, title="Synthetic", subtitle="Secondary line")
    im = cover.compose(fake_rendered(600, 200, theme.canvas), (1500, 600))
    assert_canvas(im, (1500, 600), theme.canvas, 8)
    colors = {c for _, c in im.getcolors(1 << 20)}
    hexes = {"#%02X%02X%02X" % c for c in colors}
    assert PALETTES[name]["text"] in hexes and PALETTES[name]["secondary"] in hexes


def test_palette_subtitle_key_overrides():
    theme = from_dict({"palette": {"subtitle": "#123456"}}).build_theme("x-light")
    assert theme.subtitle_color == "#123456"
    assert load_builtin("mono").subtitle_color is None  # falls back to the title color


# Edge and arrow colors, pinned to the owner-approved values. The X themes draw
# edges in X's secondary text gray rather than the border color, for legibility.
# mono, soft and warm set only lineColor; Mermaid derives the rest from it.
EDGE_COLORS = {
    "mono": {"lineColor": "#2C2C2C", "actorLineColor": None, "signalColor": None},
    "soft": {"lineColor": "#5A7380", "actorLineColor": None, "signalColor": None},
    "warm": {"lineColor": "#57534E", "actorLineColor": None, "signalColor": None},
    "x-light": {"lineColor": "#536471", "actorLineColor": "#536471", "signalColor": "#536471"},
    "x-dark": {"lineColor": "#71767B", "actorLineColor": "#71767B", "signalColor": "#71767B"},
}


def test_edge_colors_cover_every_theme():
    assert sorted(EDGE_COLORS) == sorted(BUILTIN_THEMES)


@pytest.mark.parametrize("name", sorted(EDGE_COLORS))
def test_edge_colors_are_pinned(name):
    tv = load_builtin(name).mermaid_config()["themeVariables"]
    assert {k: tv.get(k) for k in EDGE_COLORS[name]} == EDGE_COLORS[name]


@pytest.mark.parametrize("name", sorted(PALETTES))
def test_x_edges_use_secondary_text_not_border(name):
    tv = load_builtin(name).mermaid_config()["themeVariables"]
    assert tv["lineColor"] == PALETTES[name]["secondary"] != PALETTES[name]["border"]


def _patched_builtin(monkeypatch, tmp_path, name, **changes):
    from pathlib import Path

    from md2xarticle import theme as theme_mod

    shipped = Path(theme_mod.__file__).parent / "themes" / f"{name}.json"
    data = json.loads(shipped.read_text(encoding="utf-8"))
    data.update(changes)
    (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(theme_mod.resources, "files", lambda _pkg: tmp_path)


@pytest.mark.parametrize("bad", ["gray", "#53647", "#5364ZZ", ""])
def test_load_builtin_rejects_a_bad_subtitle_color(monkeypatch, tmp_path, bad):
    _patched_builtin(monkeypatch, tmp_path, "x-light", subtitle_color=bad)
    with pytest.raises(UsageError, match="RRGGBB"):
        load_builtin("x-light")


def test_load_builtin_accepts_missing_or_valid_subtitle_color(monkeypatch, tmp_path):
    _patched_builtin(monkeypatch, tmp_path, "x-light", subtitle_color="#ABCDEF")
    assert load_builtin("x-light").subtitle_color == "#ABCDEF"
    _patched_builtin(monkeypatch, tmp_path, "mono")
    assert load_builtin("mono").subtitle_color is None
