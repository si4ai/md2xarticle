"""The only module that names concrete classes. Everything else uses the bases."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from md2xarticle.compose.base import ImageComposer
from md2xarticle.compose.body import BodyImageComposer
from md2xarticle.compose.cover import CoverComposer
from md2xarticle.errors import UsageError, renderer_usage
from md2xarticle.fonts import subtitle_font_path, title_font_path
from md2xarticle.parse.base import MarkdownParser
from md2xarticle.parse.markdown_it import MarkdownItParser
from md2xarticle.pipeline import Pipeline
from md2xarticle.platform.base import Platform
from md2xarticle.platform.posix import PosixPlatform
from md2xarticle.platform.windows import WindowsPlatform
from md2xarticle.platform.wsl import WslPlatform
from md2xarticle.render.base import DiagramRenderer
from md2xarticle.render.mermaidx import MermaidxRenderer
from md2xarticle.theme import Theme
from md2xarticle.write.base import ArticleWriter
from md2xarticle.write.html import XArticleHtmlWriter
from md2xarticle.write.manifest import ManifestWriter

PARSERS: dict[str, type[MarkdownParser]] = {"markdown-it": MarkdownItParser}
RENDERERS: dict[str, type[DiagramRenderer]] = {"mermaidx": MermaidxRenderer}
BODY_COMPOSERS: dict[str, type[ImageComposer]] = {"body": BodyImageComposer}
COVER_COMPOSERS: dict[str, type[ImageComposer]] = {"cover": CoverComposer}
PLATFORMS: dict[str, type[Platform]] = {
    "posix": PosixPlatform,
    "windows": WindowsPlatform,
    "wsl": WslPlatform,
}
WRITERS: dict[str, type[ArticleWriter]] = {
    "x-article-html": XArticleHtmlWriter,
    "manifest": ManifestWriter,
}

DEFAULT_RENDERER = "mermaidx"
DEFAULT_PARSER = "markdown-it"


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
    except OSError:
        return False


def detect_platform() -> Platform:
    if sys.platform == "win32":
        return WindowsPlatform()
    if sys.platform.startswith("linux") and _is_wsl():
        return WslPlatform()
    return PosixPlatform()


def make_parser(name: str = DEFAULT_PARSER) -> MarkdownParser:
    try:
        return PARSERS[name]()
    except KeyError:
        raise UsageError(
            f"unknown parser {name!r}; available: {', '.join(sorted(PARSERS))}"
        ) from None


def make_writer(name: str = "manifest") -> ArticleWriter:
    try:
        return WRITERS[name]()
    except KeyError:
        raise UsageError(
            f"unknown writer {name!r}; available: {', '.join(sorted(WRITERS))}"
        ) from None


def make_renderer(name: str, article: str | Path = "article.md") -> DiagramRenderer:
    cls = RENDERERS.get(name)
    if cls is None:
        raise renderer_usage(name, article=article)
    renderer = cls()
    if not renderer.available():
        raise renderer_usage(name, article=article)
    return renderer


def build_pipeline(
    theme: Theme,
    renderer: str = DEFAULT_RENDERER,
    platform: Platform | None = None,
    article: str | Path = "article.md",
) -> Pipeline:
    platform = platform or detect_platform()
    font = title_font_path(platform.font_dirs())
    sub_font = subtitle_font_path(platform.font_dirs())

    def make_cover(title: str | None, subtitle: str | None = None) -> ImageComposer:
        return CoverComposer(theme, title=title, font_path=font, subtitle=subtitle, subtitle_font_path=sub_font)

    return Pipeline(
        parser=MarkdownItParser(),
        renderer=make_renderer(renderer, article=article),
        body=BodyImageComposer(theme),
        make_cover=make_cover,
        platform=platform,
        theme=theme,
    )
