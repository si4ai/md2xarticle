"""Test helpers shared by the suites."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from md2xarticle.compose.measure import MIN_MARGIN_FRACTION, measure
from md2xarticle.model import RenderedImage
from md2xarticle.theme import hex_to_rgb, load_builtin

HERE = Path(__file__).parent
SNAPSHOTS = HERE / "snapshots"
FIXTURE_MD = SNAPSHOTS / "synthetic_article.md"


def fake_rendered(width: int, height: int, background: str = "#F7FAFB") -> RenderedImage:
    """A vector-like stand-in for a renderer: a framed box that redraws at any scale."""

    def rasterize(scale: float) -> bytes:
        pad = max(1, round(10 * scale))
        w, h = max(1, round(width * scale)), max(1, round(height * scale))
        im = Image.new("RGB", (w + 2 * pad, h + 2 * pad), hex_to_rgb(background))
        d = ImageDraw.Draw(im)
        d.rectangle([pad, pad, pad + w - 1, pad + h - 1], fill="#D9EEF2", outline="#2F8A8A", width=max(1, round(2 * scale)))
        buf = BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    with Image.open(BytesIO(rasterize(1))) as im:
        size = im.size
    return RenderedImage(native_size=size, background=background, rasterize=rasterize)


def assert_canvas(image: Image.Image, size: tuple[int, int], canvas: str, center_px: int) -> None:
    """Exact size, centered within ``center_px``, at least 4% margin per side."""
    assert image.size == size
    m = measure(image, hex_to_rgb(canvas))
    assert m is not None, "image has no content"
    assert m.off_center_x <= center_px, m
    assert m.off_center_y <= center_px, m
    assert min(m.left, m.right) >= MIN_MARGIN_FRACTION * size[0], m
    assert min(m.top, m.bottom) >= MIN_MARGIN_FRACTION * size[1], m
