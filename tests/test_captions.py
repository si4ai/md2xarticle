"""Caption source order: title, %% caption:, Figure line, nearest heading, Diagram NN."""

from __future__ import annotations

from md2xarticle.model import MermaidBlock
from md2xarticle.parse.markdown_it import MarkdownItParser
from md2xarticle.shape.captions import caption_for, figure_caption, mermaid_caption_comment, mermaid_title


def block(
    source: str,
    *,
    index: int = 1,
    line: int = 1,
    anchor_text: str | None = None,
    figure_text: str | None = None,
    nearest_heading: str | None = None,
) -> MermaidBlock:
    return MermaidBlock(
        index=index,
        source=source,
        line=line,
        anchor_text=anchor_text,
        figure_text=figure_text,
        nearest_heading=nearest_heading,
    )


def test_mermaid_front_matter_title_wins():
    source = "---\ntitle: From front matter\n---\nflowchart LR\n  A-->B\n%% caption: From comment\n"
    assert mermaid_title(source) == "From front matter"
    assert caption_for(block(source, figure_text="*Figure: From figure*", nearest_heading="Heading"), 1) == "From front matter"


def test_quoted_title_is_unwrapped():
    assert mermaid_title('---\ntitle: "Quoted title"\n---\nflowchart LR\n  A-->B\n') == "Quoted title"


def test_title_line_and_pie_title():
    assert mermaid_title("sequenceDiagram\n    title The protocol\n    A->>B: hi\n") == "The protocol"
    assert mermaid_title("pie title Pets adopted\n    \"Dogs\" : 2\n") == "Pets adopted"


def test_caption_comment_beats_figure_and_heading():
    source = "flowchart LR\n  A-->B\n%% caption: From comment\n"
    got = caption_for(block(source, figure_text="*Figure: From figure*", nearest_heading="Heading"), 1)
    assert got == "From comment"
    assert mermaid_caption_comment(source) == "From comment"


def test_figure_line_beats_heading():
    got = caption_for(
        block("flowchart LR\n  A-->B\n", figure_text="*Figure: From figure*", nearest_heading="Heading"),
        1,
    )
    assert got == "From figure"


def test_figure_forms():
    assert figure_caption("*Figure: Italic*") == "Italic"
    assert figure_caption("_Figure: Underscore_") == "Underscore"
    assert figure_caption("**Figure: Bold**") == "Bold"
    assert figure_caption("![Figure: Alt text](images/01.png)") == "Alt text"
    assert figure_caption("Figure: Plain") == "Plain"
    assert figure_caption("A normal sentence.") is None


def test_nearest_heading_when_nothing_else():
    got = caption_for(block("flowchart LR\n  A-->B\n", nearest_heading="Overview"), 3)
    assert got == "Overview"


def test_last_resort_diagram_number():
    got = caption_for(block("flowchart LR\n  A-->B\n", index=3), 12)
    assert got == "Diagram 03"
    got = caption_for(block("flowchart LR\n  A-->B\n", index=7), 100)
    assert got == "Diagram 007"


def test_parser_attaches_a_following_figure_line():
    text = (
        "## Section\n\n"
        "A lead-in paragraph.\n\n"
        "```mermaid\nflowchart LR\n  A-->B\n```\n\n"
        "*Figure: Request flow*\n"
    )
    doc = MarkdownItParser().parse(text)
    assert len(doc.blocks) == 1
    assert doc.blocks[0].anchor_text == "A lead-in paragraph."
    assert doc.blocks[0].figure_text == "Figure: Request flow"
    assert doc.blocks[0].nearest_heading == "Section"
    assert caption_for(doc.blocks[0], 1) == "Request flow"
