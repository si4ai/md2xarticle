"""x-light and x-dark: X's palette, with X blue as a sparing accent."""

from __future__ import annotations

import pytest

from md2xarticle import factory
from md2xarticle.customize import from_dict
from md2xarticle.theme import load_builtin
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
