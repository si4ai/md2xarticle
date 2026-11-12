"""The diagrams pipeline. Depends only on the base classes; the factory wires
in the concrete ones."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from md2xarticle.compose.base import ImageComposer
from md2xarticle.compose.measure import measure
from md2xarticle.customize import DiagramOverride
from md2xarticle.errors import DiagramRenderError, UsageError
from md2xarticle.model import Document, MermaidBlock, RenderedImage
from md2xarticle.parse.base import MarkdownParser
from md2xarticle.platform.base import Platform
from md2xarticle.render.base import DiagramRenderer
from md2xarticle.theme import Theme, hex_to_rgb
from md2xarticle.transform import set_flowchart_direction

PNG_OPTIONS = {"format": "PNG", "compress_level": 6, "optimize": False}


@dataclass(frozen=True)
class DiagramsOptions:
    out_dir: Path
    size: tuple[int, int] = (1600, 900)
    cover: bool = False
    cover_size: tuple[int, int] = (1500, 600)
    cover_diagram: int | None = None  # None means diagram 1
    cover_title_only: bool = False
    cover_title: str | None = None  # None means front matter title; "" means none
    only: frozenset[int] | None = None
    overrides: dict[int, DiagramOverride] = field(default_factory=dict)


@dataclass
class ImageResult:
    index: int
    line: int
    file: str | None = None  # relative to out_dir, forward slashes
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class DiagramsResult:
    document: Document
    images: list[ImageResult] = field(default_factory=list)
    cover: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def failed(self) -> list[ImageResult]:
        return [r for r in self.images if not r.ok]


def image_name(index: int, total: int) -> str:
    return f"{index:0{max(2, len(str(total)))}d}.png"


def save_png(image: Image.Image, path: Path) -> None:
    """Deterministic PNG: fixed compression, no metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, **PNG_OPTIONS)


class Pipeline:
    def __init__(
        self,
        parser: MarkdownParser,
        renderer: DiagramRenderer,
        body: ImageComposer,
        make_cover: Callable[[str | None], ImageComposer],
        platform: Platform,
        theme: Theme,
    ) -> None:
        self.parser = parser
        self.renderer = renderer
        self.body = body
        self.make_cover = make_cover
        self.platform = platform
        self.theme = theme

    def _source(self, block: MermaidBlock, opts: DiagramsOptions, warnings: list[str]) -> str:
        override = opts.overrides.get(block.index)
        if override is None or override.layout is None:
            return block.source
        new, changed = set_flowchart_direction(block.source, override.layout)
        if not changed:
            warnings.append(
                f"diagram {block.index:02d}: layout override applies to flowchart "
                "and graph only; rendered as written"
            )
        return new

    def _check(self, label: str, image: Image.Image, composer: ImageComposer, warnings: list[str]) -> None:
        margins = measure(image, hex_to_rgb(self.theme.canvas))
        if margins is None:
            warnings.append(f"{label}: image is empty")
            return
        for problem in margins.problems(composer.center_tolerance):
            warnings.append(f"{label}: {problem}")

    def run_diagrams(self, text: str, opts: DiagramsOptions) -> DiagramsResult:
        doc = self.parser.parse(text)
        result = DiagramsResult(document=doc)
        total = len(doc.blocks)
        if opts.only is not None:
            bad = sorted(i for i in opts.only if not 1 <= i <= total)
            if bad:
                raise UsageError(
                    f"--only {','.join(map(str, bad))}: the article has {total} diagram(s)"
                )
        for idx in opts.overrides:
            if not 1 <= idx <= total:
                result.warnings.append(f"customization: diagram {idx} does not exist")

        rendered: dict[int, RenderedImage] = {}
        images_dir = opts.out_dir / "images"
        for block in doc.blocks:
            if opts.only is not None and block.index not in opts.only:
                continue
            item = ImageResult(index=block.index, line=block.line)
            result.images.append(item)
            try:
                img = self.renderer.render(self._source(block, opts, result.warnings), self.theme)
            except DiagramRenderError as exc:
                item.error = str(exc)
                continue
            rendered[block.index] = img
            composed = self.body.compose(img, opts.size)
            name = image_name(block.index, total)
            save_png(composed, images_dir / name)
            item.file = f"images/{name}"
            self._check(f"image {block.index:02d}", composed, self.body, result.warnings)

        if opts.cover:
            result.cover = self._cover(doc, opts, rendered, result.warnings)
        return result

    def _cover(
        self,
        doc: Document,
        opts: DiagramsOptions,
        rendered: dict[int, RenderedImage],
        warnings: list[str],
    ) -> str | None:
        title = doc.title if opts.cover_title is None else (opts.cover_title or None)
        image: RenderedImage | None = None
        if not opts.cover_title_only:
            idx = opts.cover_diagram or 1
            block = next((b for b in doc.blocks if b.index == idx), None)
            if block is None:
                warnings.append(f"cover: diagram {idx} does not exist")
            elif idx in rendered:
                image = rendered[idx]
            else:
                try:
                    image = self.renderer.render(self._source(block, opts, []), self.theme)
                except DiagramRenderError:
                    warnings.append(f"cover: diagram {idx} failed to render")
        if image is None and not title:
            warnings.append("cover: no diagram and no title; cover skipped")
            return None
        composer = self.make_cover(title)
        cover = composer.compose(image, opts.cover_size)
        save_png(cover, opts.out_dir / "images" / "cover.png")
        self._check("cover", cover, composer, warnings)
        return "images/cover.png"
