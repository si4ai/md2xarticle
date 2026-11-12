"""The default theme is mono; soft and warm stay as options."""

from __future__ import annotations

import pytest

from md2xarticle import cli
from md2xarticle.customize import Customization, from_dict
from md2xarticle.theme import BUILTIN_THEMES, DEFAULT_THEME, load_builtin


def test_default_theme_is_mono():
    assert DEFAULT_THEME == "mono"
    assert Customization().build_theme(DEFAULT_THEME) == load_builtin("mono")


def test_help_names_the_default(capsys):
    with pytest.raises(SystemExit):
        cli.main(["diagrams", "--help"])
    assert "(default: mono)" in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize("name", ["soft", "warm"])
def test_other_themes_stay_selectable(name):
    assert name in BUILTIN_THEMES
    assert from_dict({"theme": name}).build_theme(DEFAULT_THEME) == load_builtin(name)


@pytest.mark.parametrize("name", BUILTIN_THEMES)
def test_no_builtin_uses_mermaid_default_theme(name):
    # Every built-in starts from Mermaid's "base" theme and sets its own palette.
    theme = load_builtin(name)
    assert theme.mermaid_theme == "base"
    assert theme.mermaid_config()["themeVariables"]["primaryColor"]


def test_mono_is_neutral():
    tv = load_builtin("mono").mermaid_config()["themeVariables"]
    for key in ("primaryColor", "primaryBorderColor", "lineColor", "primaryTextColor"):
        r, g, b = (int(tv[key][i : i + 2], 16) for i in (1, 3, 5))
        assert max(r, g, b) - min(r, g, b) <= 8, (key, tv[key])


def test_readme_names_every_theme_and_the_default():
    from tests.helpers import HERE

    readme = (HERE.parent / "README.md").read_text(encoding="utf-8")
    for name in BUILTIN_THEMES:
        assert f"`{name}`" in readme, name
    assert f"| `--theme NAME` | `{DEFAULT_THEME}` |" in readme
    assert f"the default is `{DEFAULT_THEME}`" in readme
    assert "the default is `soft`" not in readme
