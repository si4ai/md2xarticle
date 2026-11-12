"""Image markers and Article shaping."""

from __future__ import annotations

from md2xarticle.parse.markdown_it import MarkdownItParser
from md2xarticle.shape.markers import build_article, format_marker, image_file


PARSER = MarkdownItParser()


def test_image_file_and_marker_padding():
    assert image_file(1, 9) == "images/01.png"
    assert image_file(7, 100) == "images/007.png"
    assert format_marker(2, "Request flow", 9) == "[Image 02: Request flow]"
    assert format_marker(7, "Wide", 100) == "[Image 007: Wide]"


def test_build_article_from_synthetic_paragraphs():
    text = (
        "# Title\n\n"
        "## Overview\n\n"
        "The pieces fit together like this:\n\n"
        "```mermaid\nflowchart LR\n  A-->B\n```\n\n"
        "## Calls\n\n"
        "```mermaid\nsequenceDiagram\n    title The protocol\n    A->>B: hi\n```\n"
    )
    article = build_article(PARSER.parse(text), source="article.md", cover="images/cover.png")
    assert article.source == "article.md"
    assert article.cover == "images/cover.png"
    assert len(article.images) == 2
    first, second = article.images
    assert first.order == 1
    assert first.file == "images/01.png"
    assert first.marker == "[Image 01: Overview]"
    assert first.caption == "Overview"
    assert first.anchor_text == "The pieces fit together like this:"
    assert first.source_line == 8
    assert second.marker == "[Image 02: The protocol]"
    assert second.caption == "The protocol"
    assert second.anchor_text is None


def test_included_omits_failed_or_skipped_diagrams():
    text = (
        "```mermaid\nflowchart LR\n  A-->B\n```\n\n"
        "```mermaid\nflowchart LR\n  C-->D\n```\n"
    )
    doc = PARSER.parse(text)
    article = build_article(doc, included={2: "images/02.png"})
    assert [ref.order for ref in article.images] == [2]
    assert article.images[0].file == "images/02.png"
    assert article.images[0].caption == "Diagram 02"


def test_empty_document():
    article = build_article(PARSER.parse(""), source="empty.md")
    assert article.source == "empty.md"
    assert article.images == ()
    assert article.cover is None


NESTED = {
    "bullet list": "Intro.\n\n- Step one:\n\n  ```mermaid\n  flowchart LR\n    A-->B\n  ```\n",
    "ordered list": "Intro.\n\n1. Step one:\n\n   ```mermaid\n   flowchart LR\n     A-->B\n   ```\n",
    "blockquote": "Intro.\n\n> Quoted:\n>\n> ```mermaid\n> flowchart LR\n>   A-->B\n> ```\n",
}


def test_nested_mermaid_fences_are_found():
    for name, text in NESTED.items():
        doc = PARSER.parse("# Title\n\n## Part\n\n" + text)
        assert len(doc.blocks) == 1, name
        block = doc.blocks[0]
        assert block.source.startswith("flowchart LR\n"), name
        assert block.line == 10, name  # first source line, 1-based
        assert block.nearest_heading == "Part", name
        assert block.anchor_text is None and block.figure_text is None, name


def test_nested_and_top_level_fences_keep_reading_order():
    text = (
        "# Title\n\n"
        "```mermaid\nflowchart LR\n  A-->B\n```\n\n"
        "- item\n\n  ```mermaid\n  flowchart TD\n    C-->D\n  ```\n\n"
        "```mermaid\npie\n  \"x\": 1\n```\n"
    )
    doc = PARSER.parse(text)
    assert [b.index for b in doc.blocks] == [1, 2, 3]
    assert [b.source.split()[0] for b in doc.blocks] == ["flowchart", "flowchart", "pie"]
    assert doc.blocks[1].source.startswith("flowchart TD")
