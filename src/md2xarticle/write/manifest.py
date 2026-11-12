"""``ManifestWriter``: write ``manifest.json`` for the X Article image upload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from md2xarticle.model import Article, ImageRef
from md2xarticle.write.base import ArticleWriter

MANIFEST_VERSION = 1
MANIFEST_NAME = "manifest.json"


def _image_entry(ref: ImageRef) -> dict:
    return {
        "order": ref.order,
        "file": ref.file,
        "marker": ref.marker,
        "caption": ref.caption,
        "anchor_text": ref.anchor_text,
        "source_line": ref.source_line,
    }


def _as_article(article: Any) -> Article:
    if isinstance(article, Article):
        return article
    images = getattr(article, "images", ())
    return Article(
        source=getattr(article, "source", "article.md") or "article.md",
        images=tuple(images),
        cover=getattr(article, "cover", None),
    )


def manifest_dict(article: Any) -> dict:
    """The manifest document, with a stable key order."""
    shaped = _as_article(article)
    return {
        "version": MANIFEST_VERSION,
        "source": shaped.source,
        "cover": shaped.cover,
        "images": [_image_entry(ref) for ref in shaped.images],
    }


def manifest_text(article: Any) -> str:
    """Byte-stable JSON: two-space indent, a trailing newline, no reordering."""
    return json.dumps(manifest_dict(article), indent=2, ensure_ascii=False) + "\n"


class ManifestWriter(ArticleWriter):
    """Writes ``manifest.json`` into ``out_dir``."""

    name = "manifest"

    def write(self, article: Any, out_dir: Path) -> list[Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / MANIFEST_NAME
        path.write_text(manifest_text(article), encoding="utf-8")
        return [path]
