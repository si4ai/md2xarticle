from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ArticleWriter(ABC):
    """Writes one output format (article HTML, manifest) into ``out_dir``.

    ``XArticleHtmlWriter`` (``write/html.py``) writes ``article.html`` and
    ``outline.txt``; ``ManifestWriter`` lands later in Phase 2.
    """

    name: str = ""

    @abstractmethod
    def write(self, article: Any, out_dir: Path) -> list[Path]:
        """Write files and return their paths."""
