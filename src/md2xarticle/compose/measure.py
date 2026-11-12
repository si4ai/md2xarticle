"""Measure where content sits on a canvas. Used by composers and by tests."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageChops

BG_TOLERANCE = 16
MIN_MARGIN_FRACTION = 0.04


def content_bbox(
    image: Image.Image, background: tuple[int, int, int], tolerance: int = BG_TOLERANCE
) -> tuple[int, int, int, int] | None:
    """Box (left, top, right, bottom; right and bottom exclusive) of non-background pixels."""
    rgb = image.convert("RGB")
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, background)).convert("L")
    return diff.point(lambda p: 255 if p > tolerance else 0).getbbox()


@dataclass(frozen=True)
class Margins:
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int

    @property
    def off_center_x(self) -> int:
        return abs(self.left - self.right)

    @property
    def off_center_y(self) -> int:
        return abs(self.top - self.bottom)

    def problems(
        self, center_tolerance: int, min_fraction: float = MIN_MARGIN_FRACTION
    ) -> list[str]:
        out = []
        if self.off_center_x > center_tolerance:
            out.append(f"off center horizontally by {self.off_center_x}px")
        if self.off_center_y > center_tolerance:
            out.append(f"off center vertically by {self.off_center_y}px")
        if min(self.left, self.right) < min_fraction * self.width:
            out.append(f"side margin under {min_fraction:.0%}")
        if min(self.top, self.bottom) < min_fraction * self.height:
            out.append(f"top or bottom margin under {min_fraction:.0%}")
        return out


def measure(image: Image.Image, background: tuple[int, int, int]) -> Margins | None:
    box = content_bbox(image, background)
    if box is None:
        return None
    w, h = image.size
    left, top, right, bottom = box
    return Margins(left, top, w - right, h - bottom, w, h)
