from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from md2xarticle.compose.base import ImageComposer
from md2xarticle.compose.fit import fit
from md2xarticle.model import RenderedImage
from md2xarticle.theme import Theme, hex_to_rgb

TITLE_HEIGHT = 0.09  # starting title font size, fraction of canvas height
SUBTITLE_HEIGHT = 0.05  # starting subtitle font size, fraction of canvas height
SUBTITLE_GAP = 0.025  # space between title and subtitle, fraction of canvas height
TITLE_GAP = 0.05  # space between the text and the diagram, fraction of canvas height
MIN_FONT_PX = 10

_Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


class CoverComposer(ImageComposer):
    """5:2 cover: an optional title and subtitle above an optional diagram,
    centered as one block."""

    name = "cover"
    ratio = (5, 2)
    default_size = (1500, 600)

    def __init__(
        self,
        theme: Theme,
        title: str | None = None,
        font_path: Path | None = None,
        subtitle: str | None = None,
        subtitle_font_path: Path | None = None,
    ) -> None:
        super().__init__(theme)
        self.title = title or None
        self.subtitle = subtitle or None
        self.font_path = font_path
        self.subtitle_font_path = subtitle_font_path or font_path

    @property
    def center_tolerance(self) -> int:
        return 8 if (self.title or self.subtitle) else 4

    @staticmethod
    def _font(path: Path | None, px: int) -> _Font:
        if path is not None:
            return ImageFont.truetype(str(path), size=px)
        return ImageFont.load_default(size=px)

    @classmethod
    def _text_layout(cls, text: str, path: Path | None, start_px: int, max_w: int):
        """The largest font from ``start_px`` down whose text fits ``max_w``."""
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        px = max(MIN_FONT_PX, start_px)
        while True:
            font = cls._font(path, px)
            box = draw.textbbox((0, 0), text, font=font)
            if box[2] - box[0] <= max_w or px <= MIN_FONT_PX:
                return font, box
            px = max(MIN_FONT_PX, int(px * 0.9))

    def compose(self, image: RenderedImage | None, size: tuple[int, int]) -> Image.Image:
        self.check_size(size)
        cw, ch = size
        canvas = Image.new("RGB", size, hex_to_rgb(self.theme.canvas))
        m = self.theme.margin
        avail_w, avail_h = round(cw * (1 - 2 * m)), round(ch * (1 - 2 * m))

        lines: list[tuple[str, _Font, tuple[int, int, int, int]]] = []
        if self.title:
            font, box = self._text_layout(self.title, self.font_path, round(ch * TITLE_HEIGHT), avail_w)
            lines.append((self.title, font, box))
        if self.subtitle:
            font, box = self._text_layout(
                self.subtitle, self.subtitle_font_path, round(ch * SUBTITLE_HEIGHT), avail_w
            )
            lines.append((self.subtitle, font, box))
        sub_gap = round(ch * SUBTITLE_GAP)
        text_h = sum(b[3] - b[1] for _, _, b in lines) + sub_gap * max(0, len(lines) - 1)

        fitted = None
        gap = round(ch * TITLE_GAP) if lines else 0
        if image is not None:
            box = (avail_w, max(1, avail_h - text_h - gap))
            fitted = fit(image, box, self.theme.canvas, self.theme.max_scale)
        if fitted is None:
            gap = 0

        block_h = text_h + gap + (fitted.height if fitted is not None else 0)
        y = (ch - block_h) // 2
        draw = ImageDraw.Draw(canvas)
        for text, font, tbox in lines:
            tw = tbox[2] - tbox[0]
            draw.text(((cw - tw) // 2 - tbox[0], y - tbox[1]), text, font=font, fill=self.theme.title_color)
            y += tbox[3] - tbox[1] + sub_gap
        if lines:
            y += gap - sub_gap
        if fitted is not None:
            canvas.paste(fitted, ((cw - fitted.width) // 2, y))
        return canvas
