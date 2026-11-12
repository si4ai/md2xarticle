"""Plain data passed between the pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class MermaidBlock:
    """One fenced Mermaid block.

    ``index`` is 1-based in reading order. ``line`` is the 1-based line in the
    Markdown file where the diagram source starts (the line after the fence).
    """

    index: int
    source: str
    line: int


@dataclass(frozen=True)
class Heading:
    """One Markdown heading.

    ``level`` is 1 for ``#``, 2 for ``##``, and so on. ``line`` is the
    1-based line in the Markdown file. ``preceded_by_content`` is True
    when a non-heading block sits between the previous heading (or the
    start of the body) and this one.
    """

    level: int
    text: str
    line: int
    preceded_by_content: bool = False


@dataclass(frozen=True)
class Document:
    title: str | None = None
    subtitle: str | None = None
    blocks: tuple[MermaidBlock, ...] = ()
    headings: tuple[Heading, ...] = ()


@dataclass(frozen=True)
class RenderedImage:
    """A rendered diagram that can be rasterized at any scale.

    ``native_size`` is the pixel size at scale 1. ``rasterize(scale)`` returns
    PNG bytes drawn on ``background``. Vector renderers re-rasterize so the
    composer never has to upscale pixels.
    """

    native_size: tuple[int, int]
    background: str
    rasterize: Callable[[float], bytes] = field(repr=False, compare=False)
