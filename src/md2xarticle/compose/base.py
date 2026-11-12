from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image

from md2xarticle.model import RenderedImage
from md2xarticle.theme import Theme


class ImageComposer(ABC):
    """Places a rendered diagram on a fixed-size canvas.

    Output is exactly ``size``, content centered within ``center_tolerance``
    pixels, with at least 4% margin on every side.
    """

    name: str = ""
    ratio: tuple[int, int] = (16, 9)
    default_size: tuple[int, int] = (1600, 900)

    def __init__(self, theme: Theme) -> None:
        self.theme = theme

    @property
    def center_tolerance(self) -> int:
        return 4

    def diagram_box(self, size: tuple[int, int]) -> tuple[int, int]:
        """The largest box the diagram is fitted into on a ``size`` canvas."""
        m = self.theme.margin
        return round(size[0] * (1 - 2 * m)), round(size[1] * (1 - 2 * m))

    @abstractmethod
    def compose(self, image: RenderedImage | None, size: tuple[int, int]) -> Image.Image:
        """Return an RGB image of exactly ``size``."""

    def check_size(self, size: tuple[int, int]) -> None:
        w, h = size
        rw, rh = self.ratio
        if w <= 0 or h <= 0 or w * rh != h * rw:
            raise ValueError(f"{self.name} canvas must be {rw}:{rh}, got {w}x{h}")
