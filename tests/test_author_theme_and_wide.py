"""A diagram's own %%{init}%% theme is kept, and a wide flowchart is drawn
compact when that reads larger on 16:9. Real renderer."""

from __future__ import annotations

import pytest

from md2xarticle.render.mermaidx import MermaidxRenderer, has_author_theme
from md2xarticle.theme import load_builtin

RENDERER = MermaidxRenderer()
pytestmark = pytest.mark.skipif(not RENDERER.available(), reason="mermaidx not installed")

AUTHOR_COLORS = (
    '%%{init: {"theme":"base","themeVariables":{"primaryColor":"#AB12CD","lineColor":"#12AB34"}}}%%\n'
    "flowchart LR\n  A[Alpha] --> B[Beta]\n"
)
# Wider than 16:9, with edge labels between ranks and dotted side edges.
WIDE = """flowchart LR
  A([Stage one]) -->|hands off| B([Stage two])
  B -->|hands off| C([Stage three])
  C -->|hands off| D([Stage four])
  D -->|loops back| A
  A -.-> E((Sink))
  B -.-> E
  C -.-> E
  D -.-> E
"""


def svg(source: str, theme) -> str:
    return RENDERER._best_svg(source, theme).upper()


def test_detects_author_theme():
    assert has_author_theme(AUTHOR_COLORS)
    assert has_author_theme("%%{init: {'theme':'dark'}}%%\nflowchart LR\n  A-->B\n")
    assert has_author_theme("%%{ initialize: { \"themeVariables\": {} } }%%\ngraph TD\n  A-->B\n")
    assert not has_author_theme("%%{init: {\"flowchart\": {\"curve\": \"linear\"}}}%%\nflowchart LR\n  A-->B\n")
    assert not has_author_theme("flowchart LR\n  %% theme is a word in a comment\n  A-->B\n")


@pytest.mark.parametrize("name", ["mono", "x-dark"])
def test_author_theme_variables_win(name):
    out = svg(AUTHOR_COLORS, load_builtin(name))
    assert "#AB12CD" in out and "#12AB34" in out


def test_author_theme_name_wins():
    dark = "%%{init: {'theme':'dark'}}%%\nflowchart LR\n  A-->B\n"
    plain = "flowchart LR\n  A-->B\n"
    theme = load_builtin("mono")
    assert svg(dark, theme) != svg(plain, theme)
    # Built-in palette still applies without a directive.
    assert theme.theme_variables["primaryColor"].upper() in svg(plain, theme)


def _fit(img, size=(1600, 900), margin=0.06, cap=3.0):
    w, h = img.native_size
    return min(size[0] * (1 - 2 * margin) / w, size[1] * (1 - 2 * margin) / h, cap)


def test_wide_flowchart_draws_larger():
    theme = load_builtin("mono")
    plain = theme.with_overrides(compact_tall=False)
    assert _fit(RENDERER.render(WIDE, theme)) >= 1.1 * _fit(RENDERER.render(WIDE, plain))


def test_wide_render_is_deterministic():
    theme = load_builtin("mono")
    assert RENDERER.render(WIDE, theme).rasterize(1) == RENDERER.render(WIDE, theme).rasterize(1)
