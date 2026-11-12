"""Restructure Markdown headings into X Article's two heading levels."""

from __future__ import annotations

from dataclasses import dataclass

from md2xarticle.errors import UsageError
from md2xarticle.model import Document, Heading

# --heading-map values. "auto" picks between the two README tables:
# "shifted" when a "#" heading is the article title, otherwise "flat".
MAP_AUTO = "auto"
MAP_SHIFTED = "shifted"
MAP_FLAT = "flat"
MAP_CHOICES = (MAP_AUTO, MAP_SHIFTED, MAP_FLAT)

KIND_HEADING = "H"
KIND_SUBHEADING = "SH"
KIND_LEAD_IN = "lead-in"
KIND_LIST_ITEM = "list-item"

# Deep headings (#### and below) become list items when a run of two or
# more siblings at the same level has no non-heading content between them.
_DEEP = 4


@dataclass(frozen=True)
class OutlineEntry:
    kind: str
    text: str
    source_level: int
    line: int
    fallback: bool = False


@dataclass(frozen=True)
class Outline:
    title: str | None
    mapping: str
    heading_map: str
    entries: tuple[OutlineEntry, ...]

    @property
    def fallbacks(self) -> tuple[OutlineEntry, ...]:
        return tuple(e for e in self.entries if e.fallback)


def first_h1(doc: Document) -> Heading | None:
    return next((h for h in doc.headings if h.level == 1), None)


def article_title(doc: Document) -> str | None:
    """Front matter ``title``, else the text of the first ``#`` heading."""
    if doc.title:
        return doc.title
    heading = first_h1(doc)
    return heading.text if heading is not None else None


def resolve_mapping(doc: Document, heading_map: str = MAP_AUTO) -> str:
    if heading_map not in MAP_CHOICES:
        raise UsageError(
            f"unknown --heading-map {heading_map!r}; "
            f"available: {', '.join(MAP_CHOICES)}"
        )
    if heading_map != MAP_AUTO:
        return heading_map
    # "When the document uses a single # as that title"
    return MAP_SHIFTED if first_h1(doc) is not None else MAP_FLAT


def _body_headings(doc: Document) -> tuple[Heading, ...]:
    """Drop the first ``#``, which is the article title and not in the body."""
    skipped = False
    out: list[Heading] = []
    for heading in doc.headings:
        if not skipped and heading.level == 1:
            skipped = True
            continue
        out.append(heading)
    return tuple(out)


def _list_item_flags(headings: tuple[Heading, ...]) -> tuple[bool, ...]:
    flags = [False] * len(headings)
    i = 0
    while i < len(headings):
        heading = headings[i]
        if heading.level < _DEEP:
            i += 1
            continue
        j = i + 1
        while (
            j < len(headings)
            and headings[j].level == heading.level
            and not headings[j].preceded_by_content
        ):
            j += 1
        if j - i >= 2:
            for k in range(i, j):
                flags[k] = True
        i = j
    return tuple(flags)


def _kind(level: int, mapping: str, listed: bool) -> tuple[str, bool]:
    if level >= _DEEP:
        return (KIND_LIST_ITEM if listed else KIND_LEAD_IN), False
    if level == 3:
        return KIND_SUBHEADING, False
    if level == 2:
        return KIND_HEADING, False
    if mapping == MAP_FLAT:
        return KIND_HEADING, False
    # Shifted mapping has no row for a leftover "#".
    return KIND_HEADING, True


def restructure(doc: Document, heading_map: str = MAP_AUTO) -> Outline:
    mapping = resolve_mapping(doc, heading_map)
    headings = _body_headings(doc)
    listed = _list_item_flags(headings)
    entries = []
    for heading, is_list in zip(headings, listed, strict=True):
        kind, fallback = _kind(heading.level, mapping, is_list)
        entries.append(
            OutlineEntry(
                kind=kind,
                text=heading.text,
                source_level=heading.level,
                line=heading.line,
                fallback=fallback,
            )
        )
    return Outline(
        title=article_title(doc),
        mapping=mapping,
        heading_map=heading_map,
        entries=tuple(entries),
    )


def format_outline(outline: Outline) -> str:
    """The README sample format: H / SH / [bold lead-in] / [list item]."""
    lines = ["Outline (X levels)"]
    for entry in outline.entries:
        if entry.kind == KIND_HEADING:
            lines.append(f"  H   {entry.text}")
        elif entry.kind == KIND_SUBHEADING:
            lines.append(f"  SH    {entry.text}")
        elif entry.kind == KIND_LIST_ITEM:
            lines.append(f"          [list item] {entry.text}")
        else:
            lines.append(f"          [bold lead-in] {entry.text}")
    return "\n".join(lines) + "\n"
