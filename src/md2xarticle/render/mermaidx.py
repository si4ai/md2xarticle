from __future__ import annotations

import importlib.util
import re
from io import BytesIO
from typing import Any

from PIL import Image

from md2xarticle.errors import DiagramRenderError
from md2xarticle.model import RenderedImage
from md2xarticle.render.base import DiagramRenderer
from md2xarticle.render.svg_flowchart import close_cluster_gaps
from md2xarticle.render.svg_gitgraph import space_commit_labels
from md2xarticle.theme import Theme

# A diagram taller than 16:9 that would also shrink on the default 1600x900
# canvas gets a second, compact render; the one that fits 16:9 larger wins.
# Diagrams that already read at full size keep their spacing.
DEFAULT_CANVAS_HEIGHT = 900
TALL_RANK_SPACING = 30
TALL_SEQUENCE = {"messageMargin": 26, "boxMargin": 8}

_KIND = re.compile(r"^\s*([A-Za-z][\w-]*)")
_TOP_DOWN = re.compile(r"^\s*(?:flowchart|graph)(?:\s+(TD|TB))?\s*(?:;|$)", re.IGNORECASE)
_SIZE = re.compile(r'viewBox="[^"\s]+ [^"\s]+ ([\d.]+) ([\d.]+)"')


def _statements(source: str) -> list[str]:
    return [ln for ln in source.splitlines() if ln.strip() and not ln.strip().startswith("%%")]


def diagram_kind(source: str) -> str:
    """The diagram keyword: "flowchart" (also for graph), "sequenceDiagram", "gitGraph", ..."""
    lines = _statements(source)
    m = _KIND.match(lines[0]) if lines else None
    if m is None:
        return ""
    word = m.group(1).split(":")[0]
    return "flowchart" if word.lower() in ("flowchart", "graph") else word


def is_top_down(source: str) -> bool:
    lines = _statements(source)
    return bool(lines and _TOP_DOWN.match(lines[0]))


def svg_size(svg: str) -> tuple[float, float]:
    m = _SIZE.search(svg)
    return (float(m.group(1)), float(m.group(2))) if m else (1.0, 1.0)

# Mermaid's "on line N" counts lines of its own preprocessed text, not the
# Markdown block, so it is dropped. The pipeline reports the block's line.
_LINE_HINT = re.compile(r" on line \d+")
_PREFIX = re.compile(r"^(Mermaid rendering failed:\s*)?(Error:\s*)?")


def clean_message(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    text = _PREFIX.sub("", text, count=1)
    return _LINE_HINT.sub("", text)


class MermaidxRenderer(DiagramRenderer):
    """Real Mermaid in embedded QuickJS, rasterized by novasvg. No Node, no browser."""

    name = "mermaidx"
    install_hint = 'pip install "mermaidx==0.11.3" "novasvg==0.11.5" "quickjs-ng==0.18.0.1"'

    def available(self) -> bool:
        try:
            return all(
                importlib.util.find_spec(mod) is not None
                for mod in ("mermaidx", "novasvg", "quickjs")
            )
        except (ImportError, ValueError):
            return False

    def _svg(self, source: str, theme: Theme, config: dict[str, Any]) -> str:
        import mermaidx

        try:
            svg = mermaidx.render(source, theme=theme.mermaid_theme, config=config).svg()
        except Exception as exc:  # the backend raises plain RuntimeError
            raise DiagramRenderError(clean_message(exc)) from exc
        kind = diagram_kind(source)
        if kind == "gitGraph":
            svg = space_commit_labels(svg)
        elif kind == "flowchart":
            svg = close_cluster_gaps(svg, float(config.get("flowchart", {}).get("padding", 15)))
        return svg

    def _best_svg(self, source: str, theme: Theme) -> str:
        """The plain render, or for a tall diagram a compact one when that
        fits a 16:9 canvas larger. Both candidates are fixed, so the choice is
        deterministic."""
        config = theme.mermaid_config()
        svg = self._svg(source, theme, config)
        if not theme.compact_tall:
            return svg
        kind = diagram_kind(source)
        if kind == "flowchart" and is_top_down(source):
            # ELK, Mermaid's default layout here, ignores rank spacing; dagre
            # honours it.
            compact = {**config, "layout": "dagre", "flowchart": {**config["flowchart"], "rankSpacing": TALL_RANK_SPACING}}
        elif kind == "sequenceDiagram":
            compact = {**config, "sequence": {**config["sequence"], **TALL_SEQUENCE}}
        else:
            return svg
        w, h = svg_size(svg)
        if h * 16 <= w * 9:
            return svg  # limited by the width already
        if h <= DEFAULT_CANVAS_HEIGHT * (1 - 2 * theme.margin):
            return svg  # fits at full size
        try:
            alt = self._svg(source, theme, compact)
        except DiagramRenderError:
            return svg
        aw, ah = svg_size(alt)
        return alt if min(16 / aw, 9 / ah) > min(16 / w, 9 / h) else svg

    def render(self, source: str, theme: Theme) -> RenderedImage:
        from mermaidx.raster import render_png

        background = theme.canvas
        svg = self._best_svg(source, theme)
        try:
            native = render_png(svg, scale=1, background=background)
        except Exception as exc:
            raise DiagramRenderError(clean_message(exc)) from exc
        with Image.open(BytesIO(native)) as im:
            size = im.size

        def rasterize(scale: float) -> bytes:
            if scale == 1:
                return native
            return render_png(svg, scale=scale, background=background)

        return RenderedImage(native_size=size, background=background, rasterize=rasterize)
