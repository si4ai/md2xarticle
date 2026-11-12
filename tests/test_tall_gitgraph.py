"""Tall diagrams read at a usable size, subgraphs lose the layout's empty
space, and slanted gitGraph labels clash with nothing. Real renderer."""

from __future__ import annotations

import re

import pytest

from md2xarticle import factory
from md2xarticle.customize import from_dict
from md2xarticle.errors import UsageError
from md2xarticle.parse.markdown_it import MarkdownItParser
from md2xarticle.pipeline import MIN_TEXT_SCALE, DiagramsOptions
from md2xarticle.render import svg_flowchart, svg_gitgraph
from md2xarticle.render.mermaidx import MermaidxRenderer
from md2xarticle.theme import load_builtin
from tests.helpers import FIXTURE_MD, SNAPSHOTS

RENDERER = MermaidxRenderer()
pytestmark = pytest.mark.skipif(not RENDERER.available(), reason="mermaidx not installed")

TALL = SNAPSHOTS / "tall.md"
SHOWCASE = SNAPSHOTS / "showcase.md"
LONG_FIRST_LABEL = """gitGraph
    commit id: "initial import of the schema"
    branch feature
    commit id: "add parser"
    checkout main
    merge feature id: "merge"
"""


def blocks(path):
    return MarkdownItParser().parse(path.read_text(encoding="utf-8")).blocks


def source(path, index):
    return next(b.source for b in blocks(path) if b.index == index)


def raw_svg(src, theme):
    import mermaidx

    return mermaidx.render(src, theme=theme.mermaid_theme, config=theme.mermaid_config()).svg()


def cluster_gaps(svg):
    """Space between each subgraph's last node and its bottom edge."""
    nodes = svg_flowchart._node_boxes(svg)
    gaps = []
    for m in svg_flowchart._CLUSTER.finditer(svg):
        x, y, w, h = (float(m.group(i)) for i in (2, 4, 6, 8))
        inside = [n[2] for n in nodes if x <= n[0] <= x + w and y <= n[1] and n[2] <= y + h]
        if inside:
            gaps.append(y + h - max(inside))
    return gaps


def fit(img, box=(1408, 792)):
    w, h = img.native_size
    return min(box[0] / w, box[1] / h)


# --- subgraph empty space ----------------------------------------------------


def test_layout_leaves_empty_space_and_the_fix_closes_it():
    theme = load_builtin("mono")
    pad = theme.flowchart["padding"]
    raw = raw_svg(source(TALL, 4), theme)
    assert max(cluster_gaps(raw)) > 100  # the layout quirk this fix is for
    fixed = svg_flowchart.close_cluster_gaps(raw, pad)
    gaps = cluster_gaps(fixed)
    assert len(gaps) == 3 and max(gaps) <= pad + 1
    assert len(svg_flowchart._node_boxes(fixed)) == len(svg_flowchart._node_boxes(raw))
    assert svg_height(fixed) < svg_height(raw)


def svg_height(svg):
    return float(re.search(r'viewBox="\S+ \S+ \S+ (\S+)"', svg).group(1))


def test_renderer_applies_the_cluster_fix():
    theme = load_builtin("mono")
    out = RENDERER._svg(source(TALL, 4), theme, theme.mermaid_config())
    assert max(cluster_gaps(out)) <= theme.flowchart["padding"] + 1


@pytest.mark.parametrize("path,index", [(SHOWCASE, 1), (FIXTURE_MD, 2), (TALL, 1)])
def test_cluster_fix_leaves_healthy_flowcharts_alone(path, index):
    theme = load_builtin("mono")
    raw = raw_svg(source(path, index), theme)
    assert svg_flowchart.close_cluster_gaps(raw, theme.flowchart["padding"]) == raw


# --- gitGraph labels ---------------------------------------------------------


GIT_GRAPHS = [
    pytest.param(source(SHOWCASE, 3), id="showcase"),
    pytest.param(source(TALL, 3), id="tall"),
    pytest.param(LONG_FIRST_LABEL, id="long-first-label"),
]


@pytest.mark.parametrize("src", GIT_GRAPHS)
@pytest.mark.parametrize("name", ["mono", "x-dark"])
def test_git_graph_labels_clash_with_nothing(src, name):
    theme = load_builtin(name)
    raw = raw_svg(src, theme)
    before = svg_gitgraph._Graph(raw)
    assert before.collisions()  # Mermaid's own spacing does clash here
    out = RENDERER._svg(src, theme, theme.mermaid_config())
    after = svg_gitgraph._Graph(out)
    assert after.usable()
    assert after.collisions() == []
    assert len(after.labels) == len(before.labels) and len(after.commits) == len(before.commits)


def test_first_label_clears_the_branch_names():
    theme = load_builtin("mono")
    raw = raw_svg(LONG_FIRST_LABEL, theme)
    graph = svg_gitgraph._Graph(raw)
    lane_y = graph.lay.lanes[1]
    rect = next(r for r in graph.branch_rects if abs(sum(y for _, y in r) / 4 - lane_y) < 20)
    first = graph._label_poly(graph.labels[0])
    assert svg_gitgraph._poly_poly(first, rect) == 0  # the first label runs into 'feature'
    out = svg_gitgraph.space_commit_labels(raw)
    after = svg_gitgraph._Graph(out)
    assert after.collisions() == []
    assert min(svg_gitgraph._poly_poly(after._label_poly(after.labels[0]), r) for r in after.branch_rects) >= svg_gitgraph.CLEAR
    # Fixed by giving the lane more room, not by pushing every commit right.
    assert after.lay.cols[0] == graph.lay.cols[0]


def test_level_labels_are_left_alone():
    theme = from_dict({"style": {"rotate_commit_labels": False}}).build_theme("mono")
    raw = raw_svg(source(SHOWCASE, 3), theme)
    assert svg_gitgraph.space_commit_labels(raw) == raw


# --- tall diagrams -------------------------------------------------------------


def run(path, theme, tmp_path):
    pipeline = factory.build_pipeline(theme)
    text = path.read_text(encoding="utf-8")
    return pipeline.run_diagrams(text, DiagramsOptions(out_dir=tmp_path, cover=True))


@pytest.mark.parametrize("name", ["mono", "x-dark"])
def test_tall_fixture_reads_at_a_usable_size(name, tmp_path):
    result = run(TALL, load_builtin(name), tmp_path)
    assert all(r.ok for r in result.images)
    body = [w for w in result.warnings if not w.startswith("cover:")]
    assert body == []  # no small-text warning, and every margin check passes
    # A top-down diagram on the wide 5:2 cover stays small; the run says so.
    assert result.warnings == [w for w in result.warnings if "scaled to" in w]


def test_compact_render_is_what_lifts_the_tall_diagrams():
    theme = load_builtin("mono")
    plain = theme.with_overrides(compact_tall=False)
    for index in (1, 2):
        src = source(TALL, index)
        assert fit(RENDERER.render(src, theme)) > fit(RENDERER.render(src, plain))
    assert fit(RENDERER.render(source(TALL, 1), plain)) < MIN_TEXT_SCALE <= fit(RENDERER.render(source(TALL, 1), theme))


@pytest.mark.parametrize("path,index", [(SHOWCASE, 1), (SHOWCASE, 2), (FIXTURE_MD, 1), (FIXTURE_MD, 2), (FIXTURE_MD, 3), (FIXTURE_MD, 4)])
def test_diagrams_that_need_no_fix_render_exactly_as_before(path, index):
    import mermaidx

    theme = load_builtin("mono")
    src = source(path, index)
    want = mermaidx.render(src, theme=theme.mermaid_theme, config=theme.mermaid_config()).png(scale=1, background=theme.canvas)
    assert RENDERER.render(src, theme).rasterize(1) == want


@pytest.mark.parametrize("index", [1, 2, 3, 4])
def test_fixed_renders_are_deterministic(index):
    theme = load_builtin("mono")
    src = source(TALL, index)
    assert RENDERER.render(src, theme).rasterize(1) == RENDERER.render(src, theme).rasterize(1)


def test_compact_tall_style_key():
    assert from_dict({"style": {"compact_tall": False}}).build_theme("mono").compact_tall is False
    assert load_builtin("mono").compact_tall is True
    with pytest.raises(UsageError):
        from_dict({"style": {"compact_tall": "no"}})
