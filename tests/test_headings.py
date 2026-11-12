"""Heading restructuring matches the README Headings section."""

from __future__ import annotations

import pytest

from md2xarticle.errors import UsageError
from md2xarticle.parse.markdown_it import MarkdownItParser
from md2xarticle.shape.headings import (
    KIND_HEADING,
    KIND_LEAD_IN,
    KIND_LIST_ITEM,
    KIND_SUBHEADING,
    MAP_FLAT,
    MAP_SHIFTED,
    format_outline,
    restructure,
)

PARSER = MarkdownItParser()

# The README sample outline, produced by a single "#" title and the shifted map.
SAMPLE_MD = """\
# Article title

## Introduction

## How it works

### The parser

### The renderer

#### Theme details

## Results
"""

SAMPLE_OUTLINE = """\
Outline (X levels)
  H   Introduction
  H   How it works
  SH    The parser
  SH    The renderer
          [bold lead-in] Theme details
  H   Results
"""


def outline(text: str, heading_map: str = "auto"):
    return restructure(PARSER.parse(text), heading_map=heading_map)


def test_readme_sample_format():
    result = outline(SAMPLE_MD)
    assert result.mapping == MAP_SHIFTED
    assert result.title == "Article title"
    assert format_outline(result) == SAMPLE_OUTLINE


def test_first_hash_is_title_and_not_in_the_body():
    result = outline("# Title\n\n## Section\n")
    assert result.title == "Title"
    assert [(e.kind, e.text) for e in result.entries] == [(KIND_HEADING, "Section")]


def test_front_matter_title_wins_and_first_hash_stays_out_of_the_body():
    text = "---\ntitle: From front matter\n---\n\n# From heading\n\n## Section\n"
    result = outline(text)
    assert result.title == "From front matter"
    assert result.mapping == MAP_SHIFTED  # a "#" heading is present
    assert [(e.kind, e.text) for e in result.entries] == [(KIND_HEADING, "Section")]


def test_auto_picks_flat_when_there_is_no_hash_title():
    result = outline("## Section\n\n### Details\n")
    assert result.title is None
    assert result.mapping == MAP_FLAT
    assert [(e.kind, e.text) for e in result.entries] == [
        (KIND_HEADING, "Section"),
        (KIND_SUBHEADING, "Details"),
    ]


def test_flat_maps_a_body_hash_to_heading_when_no_title_hash_was_stripped():
    # No first "#" to strip; a document that only uses "##" stays flat.
    result = outline("## Alpha\n\n## Beta\n")
    assert result.mapping == MAP_FLAT
    assert [e.kind for e in result.entries] == [KIND_HEADING, KIND_HEADING]


def test_leftover_hash_is_a_forced_fallback_under_shifted():
    text = "# Title\n\n## Section\n\n# Leftover\n"
    result = outline(text, heading_map=MAP_SHIFTED)
    assert result.entries[-1].text == "Leftover"
    assert result.entries[-1].kind == KIND_HEADING
    assert result.entries[-1].fallback is True
    assert result.fallbacks == (result.entries[-1],)


def test_heading_map_flat_treats_leftover_hash_as_heading_without_fallback():
    text = "# Title\n\n## Section\n\n# Extra\n"
    result = outline(text, heading_map=MAP_FLAT)
    # The first "#" is still the title and is omitted; a later "#" is Heading.
    assert result.title == "Title"
    assert result.mapping == MAP_FLAT
    assert [(e.kind, e.text, e.fallback) for e in result.entries] == [
        (KIND_HEADING, "Section", False),
        (KIND_HEADING, "Extra", False),
    ]


def test_deep_heading_is_a_bold_lead_in():
    result = outline("# Title\n\n#### Alone\n")
    assert result.entries == (
        result.entries[0],
    )
    assert result.entries[0].kind == KIND_LEAD_IN
    assert result.entries[0].text == "Alone"


def test_adjacent_same_level_deep_headings_are_list_items():
    text = "# Title\n\n#### Alpha\n#### Beta\n#### Gamma\n"
    result = outline(text)
    assert [e.kind for e in result.entries] == [KIND_LIST_ITEM, KIND_LIST_ITEM, KIND_LIST_ITEM]
    assert format_outline(result) == (
        "Outline (X levels)\n"
        "          [list item] Alpha\n"
        "          [list item] Beta\n"
        "          [list item] Gamma\n"
    )


def test_content_between_deep_headings_keeps_them_as_lead_ins():
    text = "# Title\n\n#### Alpha\n\nA paragraph.\n\n#### Beta\n"
    result = outline(text)
    assert [e.kind for e in result.entries] == [KIND_LEAD_IN, KIND_LEAD_IN]


def test_a_lone_deep_heading_is_not_a_list():
    result = outline("# Title\n\n#### Only one\n")
    assert result.entries[0].kind == KIND_LEAD_IN


def test_different_deep_levels_do_not_form_one_list():
    text = "# Title\n\n#### Alpha\n##### Nested\n#### Beta\n"
    result = outline(text)
    assert [e.kind for e in result.entries] == [KIND_LEAD_IN, KIND_LEAD_IN, KIND_LEAD_IN]


def test_setext_heading_counts_as_hash_equivalent():
    text = "Title\n=====\n\nSection\n-------\n"
    result = outline(text)
    assert result.title == "Title"
    assert result.mapping == MAP_SHIFTED
    assert [(e.kind, e.text) for e in result.entries] == [(KIND_HEADING, "Section")]


def test_empty_document():
    result = outline("")
    assert result.title is None
    assert result.entries == ()
    assert format_outline(result) == "Outline (X levels)\n"


def test_unknown_heading_map_is_a_usage_error():
    with pytest.raises(UsageError, match="unknown --heading-map"):
        outline("# Title\n", heading_map="mystery")
