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
