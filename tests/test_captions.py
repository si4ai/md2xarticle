"""Caption source order: title, %% caption:, Figure line, nearest heading, Diagram NN."""

from __future__ import annotations

import pytest

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


def test_bare_title_line_does_not_swallow_next_line():
    assert mermaid_title("title\nflowchart LR\n  A-->B\n") is None
    assert mermaid_title("flowchart LR\n  title   \n  A-->B\n") is None
    assert mermaid_caption_comment("%% caption:\nflowchart LR\n") is None
    assert mermaid_title("sequenceDiagram\n\ttitle\tTabbed name\n") == "Tabbed name"


# --- a plain italic line after a diagram -------------------------------------

FENCE = "```mermaid\nflowchart LR\n  A-->B\n```\n\n"


def parsed(after: str, before: str = "## Section\n\n"):
    return MarkdownItParser().parse(before + FENCE + after).blocks[0]


@pytest.mark.parametrize("line", ["*How the parts connect.*", "_How the parts connect._"])
def test_plain_italic_line_is_the_caption(line):
    got = parsed(line + "\n")
    assert got.italic_text == "How the parts connect."
    assert caption_for(got, 1) == "How the parts connect."


def test_figure_line_beats_an_italic_line():
    got = parsed("*Figure: Explicit*\n")
    assert caption_for(got, 1) == "Explicit"


def test_italic_line_loses_to_title_and_caption_comment():
    text = "## Section\n\n```mermaid\n%% caption: From comment\nflowchart LR\n  A-->B\n```\n\n*Italic*\n"
    assert caption_for(MarkdownItParser().parse(text).blocks[0], 1) == "From comment"


@pytest.mark.parametrize(
    "line",
    [
        "*One* and *two*.",  # two italic runs, not one italic paragraph
        "Plain words with *some* italic.",
        "**Bold only.**",
        "*Line one*\nmore text",
    ],
)
def test_partly_italic_or_bold_paragraph_is_not_a_caption(line):
    got = parsed(line + "\n")
    assert got.italic_text is None
    assert caption_for(got, 1) == "Section"


def test_italic_line_after_a_comment_still_counts():
    got = parsed("<!-- note -->\n\n*After a comment.*\n")
    assert caption_for(got, 1) == "After a comment."


def test_nested_diagram_takes_no_italic_caption():
    text = "## Section\n\n- item\n\n  ```mermaid\n  flowchart LR\n    A-->B\n  ```\n\n  *Inside the list.*\n"
    got = MarkdownItParser().parse(text).blocks[0]
    assert got.italic_text is None
    assert caption_for(got, 1) == "Section"
