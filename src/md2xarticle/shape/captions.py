"""Pick a caption for a Mermaid block.

Order (see README, Decided): a Mermaid title, a ``%% caption:`` comment,
a following Figure line, the nearest preceding heading, then ``Diagram NN``.
"""

from __future__ import annotations

import re

from md2xarticle.model import MermaidBlock

_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?\n)(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)
_YAML_TITLE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.MULTILINE | re.IGNORECASE)
# Line-scoped patterns: [ \t] never crosses a newline, so a bare ``title``
# line cannot swallow the next line as its caption.
_TITLE_LINE = re.compile(r"^[ \t]*title(?:[ \t]+|:[ \t]+)(\S.*?)[ \t]*$", re.MULTILINE | re.IGNORECASE)
_PIE_TITLE = re.compile(r"^[ \t]*pie\b(?:[ \t]+\S+)*[ \t]+title[ \t]+(\S.*?)[ \t]*$", re.MULTILINE | re.IGNORECASE)
_CAPTION_COMMENT = re.compile(r"^[ \t]*%%[ \t]*caption[ \t]*:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE | re.IGNORECASE)

_FIGURE_PATTERNS = (
    re.compile(r"^\*Figure:\s*(.+?)\*$", re.IGNORECASE),
    re.compile(r"^_Figure:\s*(.+?)_$", re.IGNORECASE),
    re.compile(r"^\*\*Figure:\s*(.+?)\*\*$", re.IGNORECASE),
    re.compile(r"^!\[Figure:\s*(.+?)\](?:\(.*\))?$", re.IGNORECASE),
    re.compile(r"^Figure:\s*(.+)$", re.IGNORECASE),
)


def _strip_wrap(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def mermaid_title(source: str) -> str | None:
    """A Mermaid ``title``: front matter, a ``title`` line, or ``pie title``."""
    m = _FRONT_MATTER.match(source)
    if m:
        got = _YAML_TITLE.search(m.group(1))
        if got:
            text = _strip_wrap(got.group(1))
            if text:
                return text
        rest = source[m.end():]
    else:
        rest = source
    for pattern in (_TITLE_LINE, _PIE_TITLE):
        got = pattern.search(rest)
        if got:
            text = _strip_wrap(got.group(1))
            if text:
                return text
    return None


def mermaid_caption_comment(source: str) -> str | None:
    m = _CAPTION_COMMENT.search(source)
    if not m:
        return None
    text = _strip_wrap(m.group(1))
    return text or None


def figure_caption(text: str | None) -> str | None:
    if not text:
        return None
    folded = " ".join(text.split())
    for pattern in _FIGURE_PATTERNS:
        m = pattern.fullmatch(folded)
        if m:
            got = _strip_wrap(m.group(1))
            if got:
                return got
    return None


def fallback_caption(order: int, total: int) -> str:
    width = max(2, len(str(total)))
    return f"Diagram {order:0{width}d}"


def caption_for(block: MermaidBlock, total: int) -> str:
    """Pick the caption for ``block`` using the decided source order."""
    for value in (
        mermaid_title(block.source),
        mermaid_caption_comment(block.source),
        figure_caption(block.figure_text),
        (block.nearest_heading or "").strip() or None,
    ):
        if value:
            return value
    return fallback_caption(block.index, total)
