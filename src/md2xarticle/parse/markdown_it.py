from __future__ import annotations

import re

from markdown_it import MarkdownIt

from md2xarticle.model import Document, MermaidBlock
from md2xarticle.parse.base import MarkdownParser

_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?\n)(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)
_TITLE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


def _split_front_matter(text: str) -> tuple[str | None, str, int]:
    """Return (title, body, number of lines removed)."""
    m = _FRONT_MATTER.match(text)
    if not m:
        return None, text, 0
    title = None
    t = _TITLE.search(m.group(1))
    if t:
        title = t.group(1)
        if len(title) >= 2 and title[0] == title[-1] and title[0] in "\"'":
            title = title[1:-1]
        title = title or None
    removed = m.group(0).count("\n")
    return title, text[m.end():], removed


class MarkdownItParser(MarkdownParser):
    """markdown-it-py (CommonMark). Front matter is read for ``title`` only."""

    name = "markdown-it"

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark")

    def parse(self, text: str) -> Document:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text.startswith("\ufeff"):
            text = text[1:]
        title, body, offset = _split_front_matter(text)
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
        return Document(title=title, blocks=tuple(blocks))
