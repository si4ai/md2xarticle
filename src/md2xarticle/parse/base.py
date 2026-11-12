from __future__ import annotations

from abc import ABC, abstractmethod

from md2xarticle.model import Document


class MarkdownParser(ABC):
    """Turns Markdown text into a ``Document``."""

    name: str = ""

    @abstractmethod
    def parse(self, text: str) -> Document:
        """Parse ``text``. Mermaid blocks keep their 1-based source line."""
