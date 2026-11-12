"""Trim a rendered diagram and size it to fit a box. Shared by the composers."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from md2xarticle.compose.measure import content_bbox
from md2xarticle.model import RenderedImage
from md2xarticle.theme import hex_to_rgb

# Rasterize this much larger than the target, then downsample, for clean edges.
SUPERSAMPLE = 1.5


def _decode(png: bytes, background: tuple[int, int, int]) -> Image.Image:
    with Image.open(BytesIO(png)) as im:
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            flat = Image.new("RGBA", rgba.size, background + (255,))
            return Image.alpha_composite(flat, rgba).convert("RGB")
        return im.convert("RGB")


def fit(
    image: RenderedImage, box: tuple[int, int], canvas: str, max_scale: float
) -> Image.Image | None:
    """Content of ``image`` trimmed, scaled to fit inside ``box``.

    Never larger than ``max_scale`` times the native size, so a tiny diagram
    is not blown up. ``None`` when the render has no visible content.
    """
    bg = hex_to_rgb(canvas)
    box_w, box_h = max(1, box[0]), max(1, box[1])
    native = _decode(image.rasterize(1), bg)
    bbox = content_bbox(native, bg)
    if bbox is None:
        return None
    nw, nh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    want = min(box_w / nw, box_h / nh, max_scale)
    limit_w, limit_h = min(box_w, nw * want), min(box_h, nh * want)

    raster_scale = max(1.0, want * SUPERSAMPLE)
    src = native if raster_scale == 1 else _decode(image.rasterize(raster_scale), bg)
    bbox = content_bbox(src, bg) or (0, 0, src.width, src.height)
    trimmed = src.crop(bbox)
    tw, th = trimmed.size
    f = min(limit_w / tw, limit_h / th)
    size = (max(1, round(tw * f)), max(1, round(th * f)))
    if size == trimmed.size:
        return trimmed
    return trimmed.resize(size, Image.Resampling.LANCZOS)
