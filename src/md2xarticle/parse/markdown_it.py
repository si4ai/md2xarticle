from __future__ import annotations

import re

from markdown_it import MarkdownIt

from md2xarticle.model import Document, Heading, MermaidBlock
from md2xarticle.parse.base import MarkdownParser

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
        blocks: list[MermaidBlock] = []
        for token in tokens:
            if token.type != "fence" or token.map is None:
                continue
            info = token.info.strip().split(maxsplit=1)
            if not info or info[0].lower() != "mermaid":
                continue
            # token.map[0] is the 0-based fence line; the source starts one line later.
            line = offset + token.map[0] + 2
            blocks.append(MermaidBlock(index=len(blocks) + 1, source=token.content, line=line))
        return Document(
            title=title,
            subtitle=subtitle,
            blocks=tuple(blocks),
            headings=_headings(tokens, offset),
        )
