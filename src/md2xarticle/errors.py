"""Error types and the Output-contract message format.

Every error prints ``error: ...`` and the exact next command to try
(``try:`` / ``or:`` lines) on stderr.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

# Planned renderer names get an install hint even before their extras ship.
KNOWN_RENDERERS = ("mermaidx", "mmdc", "mmdr")
RENDERER_INSTALL_HINTS = {
    "mermaidx": "pip install md2xarticle",
    "mmdc": 'pip install "md2xarticle[mmdc]"   (needs Node and Chromium)',
    "mmdr": 'pip install "md2xarticle[mmdr]"',
}


class Md2xError(Exception):
    """Base class for md2xarticle errors."""


class UsageError(Md2xError):
    """Bad flag, missing file, or bad customization value. Exit code 2."""

    def __init__(
        self,
        message: str,
        try_cmd: str | None = None,
        or_cmd: str | None = None,
    ) -> None:
        super().__init__(message)
        self.try_cmd = try_cmd
        self.or_cmd = or_cmd


class DiagramRenderError(Md2xError):
    """A single diagram failed to render. Exit code 1 for the run."""


def format_error(
    message: str,
    try_cmd: str | None = None,
    or_cmd: str | None = None,
) -> str:
    """``error:`` plus optional ``try:`` / ``or:`` lines, as in the README."""
    lines = [f"error: {message}"]
    if try_cmd:
        lines.append(f"try:   {try_cmd}")
    if or_cmd:
        lines.append(f"or:    {or_cmd}")
    return "\n".join(lines)


def print_error(
    message: str,
    try_cmd: str | None = None,
    or_cmd: str | None = None,
    file: TextIO | None = None,
) -> None:
    """Write a contract-shaped error to stderr."""
    print(format_error(message, try_cmd=try_cmd, or_cmd=or_cmd), file=file or sys.stderr)


def diagrams_command(article: str | Path, *flags: str) -> str:
    """Build a ``md2xarticle diagrams ARTICLE.md ...`` retry command."""
    parts = ["md2xarticle", "diagrams", str(article), *flags]
    return " ".join(parts)


def renderer_usage(name: str, article: str | Path = "article.md") -> UsageError:
    """Unknown renderer, or a known renderer that is not installed."""
    fallback = diagrams_command(article, "--renderer", "mermaidx")
    hint = RENDERER_INSTALL_HINTS.get(name)
    if hint is not None:
        return UsageError(
            f"renderer {name!r} is not installed",
            try_cmd=hint,
            or_cmd=fallback,
        )
    known = ", ".join(KNOWN_RENDERERS)
    return UsageError(
        f"unknown renderer {name!r}; known renderers: {known}",
        try_cmd=fallback,
    )


def usage_retry(
    exc: BaseException,
    *,
    article: str | Path = "article.md",
    command: str = "diagrams",
    custom_path: str | Path | None = None,
    size_flag: bool = False,
) -> str | None:
    """A ``try:`` command for a UsageError that did not carry one."""
    if isinstance(exc, UsageError) and exc.try_cmd:
        return exc.try_cmd
    msg = str(exc)
    path = str(article)
    cmd = command or "diagrams"
    if custom_path is not None and (
        "customization" in msg
        or "invalid TOML" in msg
        or "unknown key" in msg
        or str(custom_path) in msg
        or Path(str(custom_path)).name in msg
    ):
        return f"md2xarticle {cmd} {path} --custom-path {custom_path}"
    if size_flag or "--size" in msg or "must be 16:9" in msg or "must look like WxH" in msg:
        return f"md2xarticle {cmd} {path} --size 1600x900"
    if "unknown theme" in msg:
        from md2xarticle.theme import DEFAULT_THEME

        return f"md2xarticle {cmd} {path} --theme {DEFAULT_THEME}"
    if "renderer" in msg:
        return f"md2xarticle {cmd} {path} --renderer mermaidx"
    if "--only" in msg:
        return f"md2xarticle {cmd} {path} --only 1"
    if "file not found" in msg or "cannot read" in msg:
        return f"md2xarticle {cmd} {path}"
    return f"md2xarticle {cmd} --help"


def argparse_retry(message: str) -> str:
    """A ``try:`` command for an argparse usage error."""
    low = message.lower()
    if "diagram numbers start at 1" in low or "expected n[" in low:
        return "md2xarticle diagrams article.md --only 1"
    if "required" in low and "article.md" in low:
        return "md2xarticle diagrams article.md"
    return "md2xarticle --help"
