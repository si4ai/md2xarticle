from __future__ import annotations

import pytest

from md2xarticle.customize import DiagramOverride, from_dict, load, parse_size
from md2xarticle.errors import UsageError
from md2xarticle.theme import BUILTIN_THEMES, load_builtin


@pytest.mark.parametrize("name", BUILTIN_THEMES)
def test_builtin_themes_load(name):
    theme = load_builtin(name)
    assert theme.name == name
    cfg = theme.mermaid_config()
    assert "themeVariables" in cfg and "themeCSS" in cfg
    assert f"rx: {theme.corner_radius}" in cfg["themeCSS"]


def test_unknown_theme():
    with pytest.raises(UsageError):
        load_builtin("neon")


def test_full_file(tmp_path):
    p = tmp_path / "article.toml"
    p.write_text(
        """
theme = "warm"
size = "1920x1080"
cover_size = "1000x400"
cover = "diagram:2"
cover_title = "Synthetic"

[style]
corner_radius = 4
spacing = 18
node_spacing = 40
rank_spacing = 50
edge_width = 1.5
margin = 0.08

[palette]
canvas = "#FFFFFF"
title = "#000000"
primary = "#112233"
line = "#445566"

[theme_variables]
fontSize = "18px"

[[diagrams]]
id = 1
layout = "LR"
""",
        encoding="utf-8",
    )
    c = load(p)
    assert c.size == (1920, 1080)
    assert c.cover_size == (1000, 400)
    assert c.cover_diagram == 2
    assert c.cover_title == "Synthetic"
    assert c.diagrams == {1: DiagramOverride(layout="LR")}
    theme = c.build_theme("soft")
    assert theme.name == "warm"
    assert theme.canvas == "#FFFFFF" and theme.title_color == "#000000"
    assert theme.corner_radius == 4 and theme.margin == 0.08 and theme.edge_width == 1.5
    assert theme.flowchart["padding"] == 18
    assert theme.flowchart["nodeSpacing"] == 40 and theme.flowchart["rankSpacing"] == 50
    assert theme.theme_variables["primaryColor"] == "#112233"
    assert theme.theme_variables["lineColor"] == "#445566"
    assert theme.theme_variables["fontSize"] == "18px"
    # Built-ins are not mutated by overrides.
    assert load_builtin("warm").canvas != "#FFFFFF"


def test_empty_file_means_defaults(tmp_path):
    p = tmp_path / "empty.toml"
    p.write_text("", encoding="utf-8")
    c = load(p)
    assert c.build_theme("soft") == load_builtin("soft")


@pytest.mark.parametrize(
    "data",
    [
        {"them": "soft"},
        {"theme": "neon"},
        {"size": "1000x1000"},
        {"cover_size": "1600x900"},
        {"cover": "diagram:x"},
        {"cover": "diagram:0"},
        {"cover": 3},
        {"style": {"margin": 0.01}},
        {"style": {"corner_radius": -1}},
        {"style": {"radius": 3}},
        {"palette": {"canvas": "white"}},
        {"palette": {"background": "#FFFFFF"}},
        {"diagrams": [{"layout": "LR"}]},
        {"diagrams": [{"id": 1, "layout": "XY"}]},
        {"diagrams": [{"id": 1, "zoom": 2}]},
    ],
)
def test_bad_values_are_usage_errors(data):
    with pytest.raises(UsageError):
        from_dict(data)


def test_missing_and_invalid_files(tmp_path):
    with pytest.raises(UsageError):
        load(tmp_path / "missing.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("theme = ", encoding="utf-8")
    with pytest.raises(UsageError):
        load(bad)


@pytest.mark.parametrize("text,ok", [("1600x900", True), ("1280X720", True), ("1600x901", False), ("abc", False), ("0x0", False)])
def test_parse_size(text, ok):
    if ok:
        assert parse_size(text, (16, 9), "size")
    else:
        with pytest.raises(UsageError):
            parse_size(text, (16, 9), "size")
