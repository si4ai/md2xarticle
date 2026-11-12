"""Build image markers and an ``Article`` of ``ImageRef``s for the writers."""

from __future__ import annotations

from md2xarticle.model import Article, Document, ImageRef
from md2xarticle.shape.captions import caption_for


def image_file(order: int, total: int) -> str:
    """``images/NN.png``, padded the same way as ``pipeline.image_name``."""
    width = max(2, len(str(total)))
    return f"images/{order:0{width}d}.png"


def format_marker(order: int, caption: str, total: int) -> str:
    width = max(2, len(str(total)))
    return f"[Image {order:0{width}d}: {caption}]"


def build_article(
    doc: Document,
    *,
    source: str = "article.md",
    cover: str | None = None,
    included: dict[int, str] | None = None,
) -> Article:
    """Shape ``doc`` into an ``Article``.

    ``included`` maps 1-based diagram index to the written file path
    (``images/01.png``). ``None`` means every Mermaid block is included,
    with default file names. Pass only the diagrams that were written
    (successful renders) when building a manifest after ``diagrams``.
    ``source`` should be a file name, not a path.
    """
    total = len(doc.blocks)
    refs: list[ImageRef] = []
    for block in doc.blocks:
        if included is not None and block.index not in included:
            continue
        caption = caption_for(block, total)
        file = included[block.index] if included is not None else image_file(block.index, total)
        refs.append(
            ImageRef(
                order=block.index,
                file=file,
                marker=format_marker(block.index, caption, total),
                caption=caption,
                anchor_text=block.anchor_text,
                source_line=block.line,
            )
        )
    return Article(source=source, images=tuple(refs), cover=cover)
