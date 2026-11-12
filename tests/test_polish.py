"""Phase 1 polish: cover subtitle, upscale cap, label wrapping, small-text
warning, gitGraph labels, and --custom-path precedence."""

from __future__ import annotations

import pytest
from PIL import Image

from md2xarticle import cli, factory
from md2xarticle.compose.measure import content_bbox, measure
from md2xarticle.customize import DiagramOverride, from_dict
from md2xarticle.errors import DiagramRenderError, UsageError
from md2xarticle.pipeline import MIN_TEXT_SCALE, WIDE_WRAP, DiagramsOptions, Pipeline
from md2xarticle.render.base import DiagramRenderer
from md2xarticle.theme import BUILTIN_THEMES, hex_to_rgb, load_builtin
from tests.helpers import FIXTURE_MD, SNAPSHOTS, assert_canvas, fake_rendered

SHOWCASE = SNAPSHOTS / "showcase.md"

# --- front matter subtitle ---------------------------------------------------


def test_parser_reads_subtitle():
    parser = factory.PARSERS["markdown-it"]()
    doc = parser.parse("---\ntitle: T\nsubtitle: 'A short line'\n---\n\n# T\n")
    assert (doc.title, doc.subtitle) == ("T", "A short line")
    assert parser.parse("---\ntitle: T\n---\n").subtitle is None
    assert parser.parse("no front matter").subtitle is None


@pytest.mark.parametrize("theme_name", BUILTIN_THEMES)
@pytest.mark.parametrize(
    ("title", "subtitle", "with_image"),
    [
        ("Pipeline Sketch", "A made-up example", True),
        ("Pipeline Sketch", "A made-up example", False),
        (None, "Subtitle only", True),
        ("Title", "A very long synthetic subtitle that keeps going until it has to shrink to fit the cover width", True),
    ],
)
def test_cover_with_subtitle_is_centered(theme_name, title, subtitle, with_image):
    theme = load_builtin(theme_name)
    composer = factory.COVER_COMPOSERS["cover"](theme, title=title, subtitle=subtitle)
    assert composer.center_tolerance == 8
    image = fake_rendered(600, 120, theme.canvas) if with_image else None
    out = composer.compose(image, (1500, 600))
    assert_canvas(out, (1500, 600), theme.canvas, 8)


def test_subtitle_adds_text_between_title_and_diagram(soft_theme):
    cover = factory.COVER_COMPOSERS["cover"]
    image = fake_rendered(600, 120, soft_theme.canvas)
    plain = cover(soft_theme, title="Title").compose(image, (1500, 600))
    both = cover(soft_theme, title="Title", subtitle="Subtitle").compose(image, (1500, 600))
    bg = hex_to_rgb(soft_theme.canvas)
    assert plain.tobytes() != both.tobytes()
    # Same overall block, taller with the subtitle line.
    p, b = content_bbox(plain, bg), content_bbox(both, bg)
    assert (b[3] - b[1]) > (p[3] - p[1])


# --- upscaling cap -----------------------------------------------------------


@pytest.mark.parametrize("kind", ["body", "cover"])
def test_tiny_diagram_is_upscaled_at_most_3x(soft_theme, kind):
    cls = factory.BODY_COMPOSERS["body"] if kind == "body" else factory.COVER_COMPOSERS["cover"]
    composer = cls(soft_theme)
    assert soft_theme.max_scale == 3.0
    out = composer.compose(fake_rendered(40, 20, soft_theme.canvas), composer.default_size)
    left, top, right, bottom = content_bbox(out, hex_to_rgb(soft_theme.canvas))
    assert abs((right - left) - 120) <= 2 and abs((bottom - top) - 60) <= 2
    assert_canvas(out, composer.default_size, soft_theme.canvas, composer.center_tolerance)


# --- label wrapping and small-text warning, with a fake renderer -------------


class SizedRenderer(DiagramRenderer):
    """Native size depends on the flowchart wrapping width, like real labels."""

    name = "sized"

    def __init__(self, sizes: dict[int | None, tuple[int, int]], fail_wide: bool = False):
        self.sizes = sizes
        self.fail_wide = fail_wide
        self.calls: list[int | None] = []

    def available(self) -> bool:
        return True

    def render(self, source, theme):
        ww = theme.flowchart.get("wrappingWidth")
        self.calls.append(ww)
        if ww is not None and self.fail_wide:
            raise DiagramRenderError("synthetic failure")
        w, h = self.sizes.get(ww, self.sizes[None])
        return fake_rendered(w, h, theme.canvas)


def make_pipeline(renderer, theme=None):
    theme = theme or load_builtin("soft")
    return Pipeline(
        parser=factory.PARSERS["markdown-it"](),
        renderer=renderer,
        body=factory.BODY_COMPOSERS["body"](theme),
        make_cover=lambda t, s=None: factory.COVER_COMPOSERS["cover"](theme, title=t, subtitle=s),
        platform=factory.detect_platform(),
        theme=theme,
    )


FLOW_TD = "```mermaid\nflowchart TD\n  A --> B\n```\n"
SEQ = "```mermaid\nsequenceDiagram\n  A->>B: hi\n```\n"


def _run(tmp_path, renderer, text=FLOW_TD, theme=None, **opts):
    result = make_pipeline(renderer, theme).run_diagrams(text, DiagramsOptions(out_dir=tmp_path, **opts))
    with Image.open(tmp_path / "images" / "01.png") as im:
        im.load()
        return result, im


def test_height_limited_flowchart_takes_the_wider_wrap_when_it_draws_larger(tmp_path):
    r = SizedRenderer({None: (300, 900), WIDE_WRAP: (500, 600)})
    _, im = _run(tmp_path, r)
    assert r.calls == [None, WIDE_WRAP]
    # Both renders are limited by the 792 px box height; the 500x600 one is drawn
    # at 792/600 = 1.32x, so its content is about 660 px wide (264 px for 300x900).
    m = measure(im.convert("RGB"), hex_to_rgb(load_builtin("soft").canvas))
    assert abs((m.width - m.left - m.right) - 660) <= 3


def test_wider_wrap_is_dropped_when_it_draws_smaller(tmp_path):
    r = SizedRenderer({None: (300, 900), WIDE_WRAP: (2000, 900)})
    _, a = _run(tmp_path / "a", r)
    _, b = _run(tmp_path / "b", SizedRenderer({None: (300, 900)}, fail_wide=True))
    assert a.tobytes() == b.tobytes()  # both used the default-wrap render


@pytest.mark.parametrize(
    ("renderer", "text", "theme"),
    [
        (SizedRenderer({None: (1600, 200)}), FLOW_TD, None),  # already width-limited
        (SizedRenderer({None: (300, 900)}), SEQ, None),  # not a flowchart
        (SizedRenderer({None: (300, 900)}), FLOW_TD, "custom"),  # wrap width set by the user
    ],
)
def test_no_second_render(tmp_path, renderer, text, theme):
    if theme == "custom":
        theme = from_dict({"style": {"wrap_width": 250}}).build_theme("soft")
    _run(tmp_path, renderer, text, theme)
    assert len(renderer.calls) == 1


def test_failed_wide_render_keeps_the_default(tmp_path):
    result, _ = _run(tmp_path, SizedRenderer({None: (300, 900)}, fail_wide=True))
    assert result.images[0].ok


def test_small_text_warns_with_the_next_step(tmp_path):
    tall = SizedRenderer({None: (400, 2400)})
    result, _ = _run(tmp_path, tall)
    scale = 792 / 2400
    assert scale < MIN_TEXT_SCALE
    assert any(
        w.startswith(f"image 01: the diagram is scaled to {scale:.2f}x") and 'layout = "LR" for id = 1' in w
        for w in result.warnings
    ), result.warnings


def test_small_text_hint_for_non_flowchart_or_overridden(tmp_path):
    result, _ = _run(tmp_path / "s", SizedRenderer({None: (400, 2400)}), SEQ)
    assert any("split it into smaller diagrams" in w for w in result.warnings)
    result, _ = _run(tmp_path / "o", SizedRenderer({None: (400, 2400)}), overrides={1: DiagramOverride(layout="LR")})
    assert any("split it into smaller diagrams" in w for w in result.warnings)


def test_readable_diagram_does_not_warn(tmp_path):
    result, _ = _run(tmp_path, SizedRenderer({None: (700, 400)}))
    assert not [w for w in result.warnings if "text is small" in w]


# --- customization ---------------------------------------------------------


def test_wrap_width_and_cover_subtitle_keys():
    c = from_dict({"cover_subtitle": "", "style": {"wrap_width": 300}})
    assert c.cover_subtitle == ""
    assert c.build_theme("soft").flowchart["wrappingWidth"] == 300
    for bad in ({"style": {"wrap_width": 10}}, {"style": {"wrap_width": "wide"}}, {"cover_subtitle": 3}):
        with pytest.raises(UsageError):
            from_dict(bad)


@pytest.mark.parametrize("name", BUILTIN_THEMES)
def test_git_graph_label_rotation_is_a_theme_setting(name):
    # Rotated labels (Mermaid's default) stay apart when commits are close;
    # level labels read better on sparse graphs, so the file can switch them.
    assert load_builtin(name).mermaid_config()["gitGraph"] == {"rotateCommitLabel": True}
    level = from_dict({"style": {"rotate_commit_labels": False}}).build_theme(name)
    assert level.mermaid_config()["gitGraph"] == {"rotateCommitLabel": False}
    assert load_builtin(name).git_graph == {"rotateCommitLabel": True}  # built-in not mutated
    with pytest.raises(UsageError):
        from_dict({"style": {"rotate_commit_labels": "no"}})


# --- --custom-path precedence over flags (CLI, real renderer) ----------------


def test_custom_file_wins_over_theme_and_size_flags(tmp_path, capsys):
    custom = tmp_path / "article.toml"
    custom.write_text('theme = "warm"\nsize = "1280x720"\ncover_subtitle = ""\n', encoding="utf-8")
    out = tmp_path / "out"
    code = cli.main([
        "diagrams", str(FIXTURE_MD), "-o", str(out), "--only", "1", "--cover",
        "--theme", "mono", "--size", "1920x1080", "--custom-path", str(custom),
    ])
    err = capsys.readouterr().err
    assert code == 0, err
    assert "warning: --theme is overridden by the customization file" in err
    assert "warning: --size is overridden by the customization file" in err
    warm = load_builtin("warm").canvas
    with Image.open(out / "images" / "01.png") as im:
        assert_canvas(im.convert("RGB"), (1280, 720), warm, 4)
    with Image.open(out / "images" / "cover.png") as im:
        assert_canvas(im.convert("RGB"), (1500, 600), warm, 8)


def test_showcase_renders_every_theme_with_subtitled_cover(tmp_path, capsys):
    """End to end on the synthetic showcase: body images, gitGraph, and a cover
    with front matter title and subtitle, for every built-in theme."""
    for name in BUILTIN_THEMES:
        out = tmp_path / name
        assert cli.main(["diagrams", str(SHOWCASE), "-o", str(out), "--cover", "--theme", name]) == 0
        canvas = load_builtin(name).canvas
        for n in ("01", "02", "03"):
            with Image.open(out / "images" / f"{n}.png") as im:
                assert_canvas(im.convert("RGB"), (1600, 900), canvas, 4)
        with Image.open(out / "images" / "cover.png") as im:
            assert_canvas(im.convert("RGB"), (1500, 600), canvas, 8)
    assert "warning" not in capsys.readouterr().err


def test_cover_subtitle_off_switch(tmp_path, capsys):
    on, off = tmp_path / "on", tmp_path / "off"
    assert cli.main(["diagrams", str(SHOWCASE), "-o", str(on), "--only", "1", "--cover"]) == 0
    custom = tmp_path / "c.toml"
    custom.write_text('cover_subtitle = ""\n', encoding="utf-8")
    assert cli.main(["diagrams", str(SHOWCASE), "-o", str(off), "--only", "1", "--cover", "--custom-path", str(custom)]) == 0
    custom.write_text('cover_title = ""\ncover_subtitle = ""\n', encoding="utf-8")
    bare = tmp_path / "bare"
    assert cli.main(["diagrams", str(SHOWCASE), "-o", str(bare), "--only", "1", "--cover", "--custom-path", str(custom)]) == 0
    capsys.readouterr()
    covers = [(d / "images" / "cover.png").read_bytes() for d in (on, off, bare)]
    assert len(set(covers)) == 3


def test_readme_customization_example_is_valid():
    import re
    import tomllib

    from tests.helpers import HERE

    readme = (HERE.parent / "README.md").read_text(encoding="utf-8")
    example = re.search(r"```toml\n(.*?)```", readme, re.DOTALL).group(1)
    c = from_dict(tomllib.loads(example))
    assert c.cover_subtitle == "" and c.style["wrap_width"] == 280 and c.style["rotate_commit_labels"] is False
