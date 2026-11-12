from __future__ import annotations

import re

from markdown_it import MarkdownIt

from md2xarticle.model import Document, MermaidBlock
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
        blocks: list[MermaidBlock] = []
        for token in self._md.parse(body):
            if token.type != "fence" or token.map is None:
                continue
            info = token.info.strip().split(maxsplit=1)
            if not info or info[0].lower() != "mermaid":
                continue
            # token.map[0] is the 0-based fence line; the source starts one line later.
            line = offset + token.map[0] + 2
            blocks.append(MermaidBlock(index=len(blocks) + 1, source=token.content, line=line))
        return Document(title=title, subtitle=subtitle, blocks=tuple(blocks))
