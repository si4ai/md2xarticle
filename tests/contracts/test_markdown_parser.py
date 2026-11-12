"""Contract: every MarkdownParser finds Mermaid blocks in order with their source line."""

from __future__ import annotations

import pytest

from md2xarticle import factory
from md2xarticle.parse.base import MarkdownParser

PARSERS = sorted(factory.PARSERS.items())


@pytest.fixture(params=[cls for _, cls in PARSERS], ids=[n for n, _ in PARSERS])
def parser(request) -> MarkdownParser:
    return request.param()


def test_finds_mermaid_blocks_with_source_lines(parser, fixture_text):
    doc = parser.parse(fixture_text)
    lines = fixture_text.splitlines()
    assert [b.index for b in doc.blocks] == [1, 2, 3, 4, 5]
    for block in doc.blocks:
        # The reported line is the block's first source line in the Markdown file.
        assert lines[block.line - 1] == block.source.splitlines()[0]
        assert lines[block.line - 2].strip().startswith("```mermaid")
    assert doc.blocks[0].source.startswith("flowchart LR")
    assert doc.blocks[2].source.startswith("sequenceDiagram")


def test_reads_front_matter_title(parser, fixture_text):
    assert parser.parse(fixture_text).title == "Pipeline Sketch"


def test_ignores_other_fences_and_empty_text(parser):
    assert parser.parse("").blocks == ()
    doc = parser.parse("```python\nprint(1)\n```\n\n~~~mermaid\ngraph LR\n  A-->B\n~~~\n")
    assert len(doc.blocks) == 1
    assert doc.blocks[0].line == 6
    assert doc.title is None


def test_crlf_input_gives_same_lines(parser, fixture_text):
    a = parser.parse(fixture_text)
    b = parser.parse(fixture_text.replace("\n", "\r\n"))
    assert a == b


def test_finds_headings_in_order(parser, fixture_text):
    doc = parser.parse(fixture_text)
    assert [(h.level, h.text, h.line) for h in doc.headings] == [
        (1, "Pipeline Sketch", 5),
        (2, "Overview", 9),
        (2, "Decisions", 21),
        (2, "Calls", 40),
        (2, "Types", 53),
        (2, "Broken on purpose", 67),
    ]
    assert doc.headings[0].preceded_by_content is False
    assert all(h.preceded_by_content for h in doc.headings[1:])


def test_empty_text_has_no_headings(parser):
    assert parser.parse("").headings == ()


def test_fenced_hash_is_not_a_heading(parser):
    doc = parser.parse("```\n# not a heading\n```\n")
    assert doc.headings == ()
