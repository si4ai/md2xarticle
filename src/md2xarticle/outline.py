"""``md2xarticle outline ARTICLE.md``: print the restructured heading outline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from md2xarticle import factory
from md2xarticle.errors import UsageError
from md2xarticle.shape.headings import MAP_AUTO, MAP_CHOICES, format_outline, restructure

# Same codes as md2xarticle.cli; kept here to avoid a circular import.
EXIT_OK, EXIT_FINDINGS = 0, 1


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = sub.add_parser(
        "outline",
        help="print the restructured heading outline",
        description="Print the heading outline after restructuring for X Article's two levels.",
    )
    parser.add_argument("article", metavar="ARTICLE.md", type=Path)
    parser.add_argument(
        "--heading-map",
        choices=MAP_CHOICES,
        default=MAP_AUTO,
        help="override the heading restructuring (default: auto)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="full error details")
    return parser


def run(args: argparse.Namespace) -> int:
    try:
        text = args.article.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise UsageError(f"file not found: {args.article}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read {args.article}: {exc}") from None

    doc = factory.make_parser().parse(text)
    outline = restructure(doc, heading_map=args.heading_map)
    sys.stdout.write(format_outline(outline))
    for entry in outline.fallbacks:
        print(
            f"warning: heading on line {entry.line} ({entry.text!r}) has no row "
            f"in the {outline.mapping} mapping; treated as Heading",
            file=sys.stderr,
        )
        print(
            f"try:   md2xarticle outline {args.article} --heading-map flat",
            file=sys.stderr,
        )
    return EXIT_FINDINGS if outline.fallbacks else EXIT_OK
