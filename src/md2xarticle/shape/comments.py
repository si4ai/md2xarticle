"""HTML comments in the Markdown are notes for the author, never article text."""

from __future__ import annotations

import re

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_html_comments(text: str) -> str:
    """``text`` without its ``<!-- ... -->`` comments."""
    return _COMMENT.sub("", text)
