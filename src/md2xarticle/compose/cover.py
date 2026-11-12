from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from md2xarticle.compose.base import ImageComposer
from md2xarticle.compose.fit import fit
from md2xarticle.model import RenderedImage
from md2xarticle.theme import Theme, hex_to_rgb

TITLE_HEIGHT = 0.09  # starting font size, fraction of canvas height
TITLE_GAP = 0.05  # space between title and diagram, fraction of canvas height


class CoverComposer(ImageComposer):
    """5:2 cover: an optional title above an optional diagram, centered as one block."""

    name = "cover"
    ratio = (5, 2)
    default_size = (1500, 600)

    def __init__(
        self, theme: Theme, title: str | None = None, font_path: Path | None = None
    ) -> None:
        super().__init__(theme)
        self.title = title or None
        self.font_path = font_path

    @property
    def center_tolerance(self) -> int:
        return 8 if self.title else 4

    def _font(self, px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if self.font_path is not None:
            return ImageFont.truetype(str(self.font_path), size=px)
        return ImageFont.load_default(size=px)

    def _title_layout(self, max_w: int, ch: int):
        assert self.title is not None
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        px = max(10, round(ch * TITLE_HEIGHT))
        while True:
            font = self._font(px)
            box = draw.textbbox((0, 0), self.title, font=font)
            if box[2] - box[0] <= max_w or px <= 10:
                return font, box
            px = max(10, int(px * 0.9))

    def compose(self, image: RenderedImage | None, size: tuple[int, int]) -> Image.Image:
        self.check_size(size)
        cw, ch = size
        canvas = Image.new("RGB", size, hex_to_rgb(self.theme.canvas))
        m = self.theme.margin
        avail_w, avail_h = round(cw * (1 - 2 * m)), round(ch * (1 - 2 * m))

        font = tbox = None
        title_h = gap = 0
        if self.title:
            font, tbox = self._title_layout(avail_w, ch)
            title_h = tbox[3] - tbox[1]
            gap = round(ch * TITLE_GAP) if image is not None else 0

        fitted = None
        if image is not None:
            box = (avail_w, max(1, avail_h - title_h - gap))
            fitted = fit(image, box, self.theme.canvas, self.theme.max_scale)
        if fitted is None:
            gap = 0

        block_h = title_h + gap + (fitted.height if fitted is not None else 0)
        top = (ch - block_h) // 2
        if font is not None and tbox is not None:
            tw = tbox[2] - tbox[0]
            x = (cw - tw) // 2 - tbox[0]
            ImageDraw.Draw(canvas).text(
                (x, top - tbox[1]), self.title, font=font, fill=self.theme.title_color
            )
        if fitted is not None:
            canvas.paste(fitted, ((cw - fitted.width) // 2, top + title_h + gap))
        return canvas
