from __future__ import annotations

import importlib.util
import re
from io import BytesIO

from PIL import Image

from md2xarticle.errors import DiagramRenderError
from md2xarticle.model import RenderedImage
from md2xarticle.render.base import DiagramRenderer
from md2xarticle.theme import Theme

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

    def render(self, source: str, theme: Theme) -> RenderedImage:
        import mermaidx

        background = theme.canvas
        try:
            diagram = mermaidx.render(
                source, theme=theme.mermaid_theme, config=theme.mermaid_config()
            )
            diagram.svg()  # mermaidx renders lazily; force the parse here
            native = diagram.png(scale=1, background=background)
        except Exception as exc:  # the backend raises plain RuntimeError
            raise DiagramRenderError(clean_message(exc)) from exc
        with Image.open(BytesIO(native)) as im:
            size = im.size

        def rasterize(scale: float) -> bytes:
            if scale == 1:
                return native
            return diagram.png(scale=scale, background=background)

        return RenderedImage(native_size=size, background=background, rasterize=rasterize)
