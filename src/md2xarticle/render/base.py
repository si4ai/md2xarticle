from __future__ import annotations

from abc import ABC, abstractmethod

from md2xarticle.model import RenderedImage
from md2xarticle.theme import Theme


class DiagramRenderer(ABC):
    """Turns Mermaid source into a ``RenderedImage``.

    ``render`` raises ``DiagramRenderError`` for a diagram that cannot be drawn.
    Line numbers inside its message are the renderer's own and are not trusted.
    """

    name: str = ""
    install_hint: str = ""

    @abstractmethod
    def available(self) -> bool:
        """True when the backend can run on this machine. Never raises."""

    @abstractmethod
    def render(self, source: str, theme: Theme) -> RenderedImage:
        """Render one diagram."""
