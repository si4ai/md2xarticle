"""XArticleHtmlWriter: element markup, headings, markers, snapshots, determinism."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from md2xarticle.model import Document
from md2xarticle.parse.markdown_it import MarkdownItParser
from md2xarticle.shape.headings import MAP_FLAT, format_outline, restructure
from md2xarticle.write.html import (
    FLATTEN,
    NEST,
    HtmlArticle,
    HtmlOptions,
    XArticleHtmlWriter,
    image_marker,
    render_body,
    render_html,
)
from tests.helpers import SNAPSHOTS

PASTE_MD = SNAPSHOTS / "paste_test.md"
SNAPSHOT_FOR = {FLATTEN: "paste_test.html", NEST: "paste_test.nested.html"}
ALLOWED_TAGS = {
    "html", "head", "meta", "title", "body", "h2", "h3", "p", "strong", "em", "s",
    "a", "code", "pre", "ul", "ol", "li", "blockquote", "table", "thead", "tbody",
    "tr", "th", "td", "hr", "br",
}


def article(text: str, heading_map: str = "auto") -> HtmlArticle:
    return HtmlArticle(text, MarkdownItParser().parse(text), heading_map)


def body(text: str, **options) -> list[str]:
    return render_body(article(text), HtmlOptions(**options))


# --- snapshots and determinism ---------------------------------------------


@pytest.mark.parametrize("mode", [FLATTEN, NEST])
def test_paste_fixture_matches_snapshot(mode):
    text = PASTE_MD.read_text(encoding="utf-8")
    expected = (SNAPSHOTS / SNAPSHOT_FOR[mode]).read_text(encoding="utf-8")
    assert render_html(article(text), HtmlOptions(nested_lists=mode)) == expected


@pytest.mark.parametrize("mode", [FLATTEN, NEST])
def test_snapshot_uses_only_plain_semantic_tags(mode):
    html = (SNAPSHOTS / SNAPSHOT_FOR[mode]).read_text(encoding="utf-8")
    tags = set(re.findall(r"</?([a-z0-9]+)", html))
    assert tags <= ALLOWED_TAGS, tags - ALLOWED_TAGS
    assert not re.search(r"<[a-z][^>]*\s(class|style|id|on\w+)=", html)
    assert "<h1" not in html


def test_same_input_same_bytes(tmp_path):
    text = PASTE_MD.read_text(encoding="utf-8")
    a = XArticleHtmlWriter().write(article(text), tmp_path / "a")
    b = XArticleHtmlWriter().write(article(text), tmp_path / "b")
    assert [p.name for p in a] == ["article.html", "outline.txt"]
    for pa, pb in zip(a, b, strict=True):
        assert pa.read_bytes() == pb.read_bytes()


def test_writer_writes_article_and_outline(tmp_path):
    text = PASTE_MD.read_text(encoding="utf-8")
    art = article(text)
    html_path, outline_path = XArticleHtmlWriter().write(art, tmp_path)
    assert html_path.read_bytes() == render_html(art).encode("utf-8")
    assert outline_path.read_text(encoding="utf-8") == format_outline(restructure(art.document))
    assert b"\r\n" not in html_path.read_bytes()


def test_non_article_input_writes_an_empty_article(tmp_path):
    html_path, outline_path = XArticleHtmlWriter().write(object(), tmp_path)
    assert "<body>\n</body>" in html_path.read_text(encoding="utf-8")
    assert outline_path.read_text(encoding="utf-8") == "Outline (X levels)\n"


# --- headings --------------------------------------------------------------


def test_title_heading_stays_out_of_the_body():
    html = render_html(article("# The Title\n\n## Part\n\nText.\n"))
    assert "<title>The Title</title>" in html
    assert "The Title</h" not in html and "<h2>Part</h2>" in html


def test_front_matter_is_not_pasted():
    lines = body("---\ntitle: Front\n---\n\n## Part\n\nText.\n")
    assert lines == ["<h2>Part</h2>", "<p>Text.</p>"]


def test_shifted_mapping():
    lines = body("# T\n\n## A\n\n### B\n\n#### C\n\nText.\n")
    assert lines == ["<h2>A</h2>", "<h3>B</h3>", "<p><strong>C</strong></p>", "<p>Text.</p>"]


def test_flat_mapping_when_no_title_heading():
    lines = render_body(article("## A\n\n### B\n\nText.\n"))
    assert lines == ["<h2>A</h2>", "<h3>B</h3>", "<p>Text.</p>"]


def test_heading_map_override():
    lines = render_body(article("# T\n\n# Second\n\nText.\n", heading_map=MAP_FLAT))
    assert lines == ["<h2>Second</h2>", "<p>Text.</p>"]


def test_sibling_deep_headings_become_one_list():
    lines = body("## A\n\n#### one\n\n#### two\n\n##### x\n\n##### y\n\nText.\n")
    assert lines == [
        "<h2>A</h2>",
        "<ul>", "<li>one</li>", "<li>two</li>", "</ul>",
        "<ul>", "<li>x</li>", "<li>y</li>", "</ul>",
        "<p>Text.</p>",
    ]


def test_heading_text_is_plain_and_escaped():
    # Heading text is the parser's plain text (as in outline.txt), so emphasis is dropped.
    assert body("## A **b** & c < d\n") == ["<h2>A b &amp; c &lt; d</h2>"]


def test_document_that_does_not_match_the_markdown_is_rejected():
    mismatched = HtmlArticle("## A\n", MarkdownItParser().parse("## A\n\n## B\n"))
    with pytest.raises(ValueError, match="do not match"):
        render_body(mismatched)


# --- block and inline elements ---------------------------------------------


def test_paragraph_spacing_has_no_empty_paragraphs():
    lines = body("One\ntwo.\n\n\n\nThree.\n")
    assert lines == ["<p>One two.</p>", "<p>Three.</p>"]


def test_hard_break():
    assert body("a\\\nb\n") == ["<p>a<br>b</p>"]


def test_inline_styles():
    assert body("**b** *i* ~~s~~ `c<d>`\n") == [
        "<p><strong>b</strong> <em>i</em> <s>s</s> <code>c&lt;d&gt;</code></p>"
    ]


def test_link_href_is_escaped_and_title_dropped():
    lines = body('[x](https://example.com/?a=1&b=2 "T")\n')
    assert lines == ['<p><a href="https://example.com/?a=1&amp;b=2">x</a></p>']


def test_unsafe_link_is_not_a_link():
    assert "<a " not in body("[x](javascript:alert(1))\n")[0]


def test_raw_html_is_text():
    assert body("<div>hi</div>\n\na <b>c</b>\n") == [
        "<p>&lt;div&gt;hi&lt;/div&gt;</p>",
        "<p>a &lt;b&gt;c&lt;/b&gt;</p>",
    ]


def test_lists_are_tight_and_ordered_start_kept():
    assert body("- a\n\n- b\n") == ["<ul>", "<li>a</li>", "<li>b</li>", "</ul>"]
    assert body("4. a\n5. b\n") == ['<ol start="4">', "<li>a</li>", "<li>b</li>", "</ol>"]


def test_nested_list_flatten_and_nest():
    text = "- a\n  - b\n    1. c\n- d\n"
    assert body(text) == [
        "<ul>", "<li>a</li>", "<li>\u2013 b</li>", "<li>\u2013 \u2013 1. c</li>", "<li>d</li>", "</ul>",
    ]
    assert body(text, nested_lists=NEST) == [
        "<ul>", "<li>a", "<ul>", "<li>b", "<ol>", "<li>c</li>", "</ol>", "</li>", "</ul>", "</li>",
        "<li>d</li>", "</ul>",
    ]


def test_blockquote():
    assert body("> a\n>\n> b\n") == ["<blockquote>", "<p>a</p>", "<p>b</p>", "</blockquote>"]


def test_code_block_drops_language_and_escapes():
    assert body("```js\nif (a < b) {}\n```\n") == ["<pre><code>if (a &lt; b) {}</code></pre>"]


def test_table_without_alignment_styles():
    lines = body("| a | b |\n|:--|--:|\n| 1 | **2** |\n")
    assert lines == [
        "<table>", "<thead>", "<tr><th>a</th><th>b</th></tr>", "</thead>",
        "<tbody>", "<tr><td>1</td><td><strong>2</strong></td></tr>", "</tbody>", "</table>",
    ]


def test_divider():
    assert body("a\n\n---\n\nb\n") == ["<p>a</p>", "<hr>", "<p>b</p>"]


def test_markdown_image_becomes_a_placeholder():
    assert body("![A chart](c.png)\n") == ["<p>[Image: A chart]</p>"]


def test_options_reject_unknown_mode():
    with pytest.raises(ValueError, match="nested_lists"):
        HtmlOptions(nested_lists="sideways")


# --- image markers ----------------------------------------------------------


@dataclass(frozen=True)
class StubImageRef:
    """Stands in for the markers lane's ImageRef; only ``index`` and ``marker`` are read."""

    index: int
    marker: str


@dataclass(frozen=True)
class StubDocument:
    title: str | None
    subtitle: str | None
    blocks: tuple
    headings: tuple
    images: tuple[StubImageRef, ...]


MERMAID = "Intro:\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\nAfter.\n"


def test_marker_falls_back_to_a_number():
    assert body(MERMAID) == ["<p>Intro:</p>", "<p>[Image 01]</p>", "<p>After.</p>"]


def test_marker_comes_from_the_image_reference():
    doc: Document = MarkdownItParser().parse(MERMAID)
    stub = StubDocument(
        doc.title, doc.subtitle, doc.blocks, doc.headings,
        images=(StubImageRef(1, "[Image 01: A & B]"),),
    )
    lines = render_body(HtmlArticle(MERMAID, stub))  # type: ignore[arg-type]
    assert lines[1] == "<p>[Image 01: A &amp; B]</p>"


def test_marker_from_a_block_field():
    @dataclass(frozen=True)
    class Block:
        index: int
        marker: str

    doc = StubDocument(None, None, (Block(2, "[Image 02: Flow]"),), (), images=())
    assert image_marker(doc, 2) == "[Image 02: Flow]"
    assert image_marker(doc, 3) == "[Image 03]"
