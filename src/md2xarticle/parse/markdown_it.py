from __future__ import annotations

import re

from markdown_it import MarkdownIt

from md2xarticle.model import Document, Heading, MermaidBlock
from md2xarticle.parse.base import MarkdownParser
from md2xarticle.shape.captions import figure_caption

_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?\n)(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)
def _key(name: str) -> re.Pattern[str]:
    return re.compile(rf"^{name}:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


_TITLE = _key("title")
_SUBTITLE = _key("subtitle")


def _value(pattern: re.Pattern[str], front: str) -> str | None:
    m = pattern.search(front)
    if not m:
        return None
    value = m.group(1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value or None


def _split_front_matter(text: str) -> tuple[str | None, str | None, str, int]:
    """Return (title, subtitle, body, number of lines removed)."""
    m = _FRONT_MATTER.match(text)
    if not m:
        return None, None, text, 0
    front = m.group(1)
    removed = m.group(0).count("\n")
    return _value(_TITLE, front), _value(_SUBTITLE, front), text[m.end():], removed


def _inline_text(token) -> str:
    if token.type in {"text", "code_inline"}:
        return token.content
    if token.type in {"softbreak", "hardbreak"}:
        return " "
    if not token.children:
        return ""
    return "".join(_inline_text(child) for child in token.children)


def _heading_text(token) -> str:
    return " ".join(_inline_text(token).split())


def _headings(tokens, offset: int) -> tuple[Heading, ...]:
    headings: list[Heading] = []
    seen_content = False
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1:])
            text = ""
            if i + 1 < n and tokens[i + 1].type == "inline":
                text = _heading_text(tokens[i + 1])
            start = tok.map[0] if tok.map is not None else 0
            headings.append(
                Heading(
                    level=level,
                    text=text,
                    line=offset + start + 1,
                    preceded_by_content=seen_content,
                )
            )
            seen_content = False
            i += 1
            continue
        if tok.type in {"heading_close", "inline"} or tok.type.endswith("_close") or tok.hidden:
            i += 1
            continue
        if tok.nesting >= 0:
            seen_content = True
        i += 1
    return tuple(headings)



def _is_mermaid_fence(token) -> bool:
    if token.type != "fence":
        return False
    info = token.info.strip().split(maxsplit=1)
    return bool(info and info[0].lower() == "mermaid")


def _mermaid_blocks(tokens, offset: int) -> tuple[MermaidBlock, ...]:
    """Mermaid fences plus the caption/anchor context around each one."""
    events: list[tuple[str, str | None, object | None]] = []
    depth = 0
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.type == "heading_open" and depth == 0:
            text = ""
            if i + 1 < n and tokens[i + 1].type == "inline":
                text = _heading_text(tokens[i + 1])
            events.append(("heading", text, None))
            i += 1
            continue
        if _is_mermaid_fence(tok) and depth == 0:
            events.append(("mermaid", None, tok))
            i += 1
            continue
        if tok.type == "paragraph_open" and depth == 0:
            text = ""
            if i + 1 < n and tokens[i + 1].type == "inline":
                text = _heading_text(tokens[i + 1])
            events.append(("paragraph", text, None))
            i += 1
            continue
        if tok.nesting == 1:
            depth += 1
        elif tok.nesting == -1:
            depth = max(0, depth - 1)
        elif depth == 0 and tok.type not in {"heading_close", "inline", "paragraph_close"}:
            # A top-level fence, code block, list already opened, hr, etc.
            if tok.type != "fence" or not _is_mermaid_fence(tok):
                if tok.type not in {"html_inline"}:
                    # Only record a real block token, not leftover inlines.
                    if tok.type in {"fence", "code_block", "html_block", "hr"} or tok.type.endswith("_open"):
                        events.append(("other", None, None))
        i += 1

    blocks: list[MermaidBlock] = []
    last_heading: str | None = None
    for idx, (kind, text, tok) in enumerate(events):
        if kind == "heading":
            last_heading = text or None
            continue
        if kind != "mermaid" or tok is None or tok.map is None:
            continue
        prev_kind, prev_text, _ = events[idx - 1] if idx else ("other", None, None)
        next_kind, next_text, _ = events[idx + 1] if idx + 1 < len(events) else ("other", None, None)
        anchor = prev_text if prev_kind == "paragraph" and prev_text else None
        figure = next_text if next_kind == "paragraph" and figure_caption(next_text) else None
        line = offset + tok.map[0] + 2
        blocks.append(
            MermaidBlock(
                index=len(blocks) + 1,
                source=tok.content,
                line=line,
                anchor_text=anchor,
                figure_text=figure,
                nearest_heading=last_heading,
            )
        )
    return tuple(blocks)


class MarkdownItParser(MarkdownParser):
    """markdown-it-py (CommonMark). Front matter is read for ``title`` and ``subtitle``."""

    name = "markdown-it"

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark")

    def parse(self, text: str) -> Document:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text.startswith("\ufeff"):
            text = text[1:]
        title, subtitle, body, offset = _split_front_matter(text)
        tokens = self._md.parse(body)
        return Document(
            title=title,
            subtitle=subtitle,
            blocks=_mermaid_blocks(tokens, offset),
            headings=_headings(tokens, offset),
        )
