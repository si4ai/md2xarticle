from __future__ import annotations

from PIL import Image

from md2xarticle.compose.base import ImageComposer
from md2xarticle.compose.fit import fit
from md2xarticle.model import RenderedImage
from md2xarticle.theme import hex_to_rgb


class BodyImageComposer(ImageComposer):
    """16:9 body image: trim, scale to fit with even padding, center."""

    name = "body"
    ratio = (16, 9)
    default_size = (1600, 900)

    def compose(self, image: RenderedImage | None, size: tuple[int, int]) -> Image.Image:
        self.check_size(size)
        cw, ch = size
        canvas = Image.new("RGB", size, hex_to_rgb(self.theme.canvas))
        if image is None:
            return canvas
        fitted = fit(image, self.diagram_box(size), self.theme.canvas, self.theme.max_scale)
        if fitted is not None:
            canvas.paste(fitted, ((cw - fitted.width) // 2, (ch - fitted.height) // 2))
        return canvas
