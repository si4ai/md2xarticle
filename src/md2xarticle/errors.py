"""Error types shared across the package."""

from __future__ import annotations


class Md2xError(Exception):
    """Base class for md2xarticle errors."""


class UsageError(Md2xError):
    """Bad flag, missing file, or bad customization value. Exit code 2."""


class DiagramRenderError(Md2xError):
    """A single diagram failed to render. Exit code 1 for the run."""
