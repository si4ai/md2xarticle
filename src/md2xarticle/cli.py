"""Command line: ``md2xarticle diagrams`` and ``md2xarticle check``."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from md2xarticle import __version__, check, factory, outline
from md2xarticle.shape.markers import build_article
from md2xarticle.customize import Customization, load, parse_size
from md2xarticle.errors import UsageError
from md2xarticle.pipeline import DiagramsOptions, DiagramsResult
from md2xarticle.privacy import Finding, findings_as_json, format_findings, scan_text
from md2xarticle.theme import BUILTIN_THEMES, DEFAULT_THEME

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE, EXIT_INTERNAL = 0, 1, 2, 3
COMMANDS = ("diagrams", "outline", "check")


def _parse_only(text: str) -> frozenset[int]:
    try:
        values = frozenset(int(p) for p in text.split(",") if p.strip())
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected N[,N...], got {text!r}") from None
    if not values or min(values) < 1:
        raise argparse.ArgumentTypeError("diagram numbers start at 1")
    return values


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="md2xarticle", description="Markdown in, X Article out."
    )
    p.add_argument("--version", action="version", version=f"md2xarticle {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    d = sub.add_parser(
        "diagrams",
        help="render every Mermaid block to a centered 16:9 PNG, plus an optional 5:2 cover",
        description="Render every Mermaid block to a centered 16:9 PNG in OUT/images/.",
    )
    d.add_argument("article", metavar="ARTICLE.md", type=Path)
    d.add_argument("-o", "--out", type=Path, default=None, help="output folder (default: out)")
    d.add_argument("--cover", action="store_true", help="also write images/cover.png at 5:2")
    d.add_argument("--theme", choices=BUILTIN_THEMES, default=None, help=f"diagram theme (default: {DEFAULT_THEME})")
    d.add_argument("--custom-path", type=Path, default=None, metavar="FILE", help="TOML customization file")
    d.add_argument("--size", default=None, metavar="WxH", help="body image size, 16:9 (default: 1600x900)")
    d.add_argument("--only", type=_parse_only, default=None, metavar="N[,N]", help="render only these diagrams (1-based)")
    d.add_argument("--renderer", default=factory.DEFAULT_RENDERER, choices=sorted(factory.RENDERERS))
    d.add_argument("--json", action="store_true", help="print a JSON summary to stdout")
    d.add_argument("-v", "--verbose", action="store_true", help="full error details")
    check.add_scan_arguments(d, require_privacy_flag=True)
    outline.add_parser(sub)
    check.add_parser(sub)
    return p


def _short(message: str) -> str:
    """First line of a renderer error, plus the next line when the first ends in ':'."""
    lines = [ln.strip() for ln in message.splitlines() if ln.strip()]
    if not lines:
        return "unknown error"
    if lines[0].endswith(":") and len(lines) > 1:
        return f"{lines[0]} near {lines[1]!r}"
    return lines[0]


def _retry_hint(args: argparse.Namespace, index: int) -> str:
    parts = ["md2xarticle", "diagrams", str(args.article)]
    if args.custom_path is not None:
        parts += ["--custom-path", str(args.custom_path)]
    if args.theme is not None:
        parts += ["--theme", args.theme]
    parts += ["--only", str(index), "--verbose"]
    return " ".join(parts)


def _options(args: argparse.Namespace, custom: Customization, out_dir: Path, warn: list[str]) -> DiagramsOptions:
    size = (1600, 900)
    if args.size is not None:
        size = parse_size(args.size, (16, 9), "--size")
    if custom.size is not None:
        if args.size is not None and custom.size != size:
            warn.append("--size is overridden by the customization file")
        size = custom.size
    return DiagramsOptions(
        out_dir=out_dir,
        size=size,
        cover=args.cover,
        cover_size=custom.cover_size or (1500, 600),
        cover_diagram=custom.cover_diagram,
        cover_title_only=custom.cover_title_only,
        cover_title=custom.cover_title,
        cover_subtitle=custom.cover_subtitle,
        only=args.only,
        overrides=custom.diagrams,
    )


def _write_manifest(args: argparse.Namespace, out_dir: Path, result: DiagramsResult) -> str:
    included = {r.index: r.file for r in result.images if r.ok and r.file}
    article = build_article(
        result.document,
        source=args.article.name,
        cover=result.cover,
        included=included,
    )
    paths = factory.make_writer().write(article, out_dir)
    return paths[0].as_posix()


def _summary_json(
    args: argparse.Namespace,
    out_dir: Path,
    result: DiagramsResult,
    notes: list[str],
    manifest: str,
    findings: list[Finding] | None = None,
) -> dict:
    data = {
        "ok": not result.failed and not findings,
        "out_dir": out_dir.as_posix(),
        "manifest": manifest,
        "images": [
            {
                "order": r.index,
                "file": r.file,
                "source_line": r.line,
                "ok": r.ok,
                "error": r.error,
            }
            for r in result.images
        ],
        "cover": result.cover,
        "warnings": result.warnings,
        "notes": notes,
    }
    if findings is not None:
        data["privacy_findings"] = findings_as_json(args.article, findings)
    return data


def run_diagrams(args: argparse.Namespace) -> int:
    warnings: list[str] = []
    deny = check.load_deny(args.deny_list) if args.check_privacy else ()
    custom = load(args.custom_path) if args.custom_path is not None else Customization()
    if custom.theme_name and args.theme and custom.theme_name != args.theme:
        warnings.append("--theme is overridden by the customization file")
    theme = custom.build_theme(args.theme or DEFAULT_THEME)
    try:
        text = args.article.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise UsageError(f"file not found: {args.article}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read {args.article}: {exc}") from None

    platform = factory.detect_platform()
    out_dir = args.out if args.out is not None else platform.default_output_dir()
    opts = _options(args, custom, out_dir, warnings)
    pipeline = factory.build_pipeline(theme, renderer=args.renderer, platform=platform)
    result = pipeline.run_diagrams(text, opts)
    result.warnings[:0] = warnings
    notes = platform.notes()
    findings = scan_text(text, deny) if args.check_privacy else None
    manifest = _write_manifest(args, out_dir, result)

    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for r in result.failed:
        message = r.error or "unknown error"
        if not args.verbose:
            message = _short(message)
        print(
            f"error: diagram {r.index:02d} ({args.article.name} line {r.line}) "
            f"failed to render: {message}",
            file=sys.stderr,
        )
        print(f"try:   {_retry_hint(args, r.index)}", file=sys.stderr)

    if args.json:
        print(json.dumps(_summary_json(args, out_dir, result, notes, manifest, findings), indent=2))
    else:
        print(f"md2xarticle {__version__}  diagrams {args.article.name} -> {out_dir.as_posix()}/")
        for r in result.images:
            status = r.file if r.ok else "FAILED"
            print(f"  {r.index:02d}  {status}  (line {r.line})")
        if result.cover:
            print(f"  cover  {result.cover}  5:2")
        ok = sum(1 for r in result.images if r.ok)
        if not result.images:
            print("No Mermaid diagrams found.")
        print(
            f"Wrote {ok} image(s){' and a cover' if result.cover else ''} "
            f"to {out_dir.as_posix()}/images/, and {manifest}"
        )
        for n in notes:
            print(n)
        if findings is not None:
            print(format_findings(args.article, findings), end="")
    return EXIT_FINDINGS if result.failed or findings else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and not argv[0].startswith("-") and argv[0] not in COMMANDS:
        print("error: the full conversion arrives in Phase 2", file=sys.stderr)
        print(f"try:   md2xarticle diagrams {argv[0]}", file=sys.stderr)
        return EXIT_USAGE
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        if args.command == "outline":
            return outline.run(args)
        if args.command == "check":
            return check.run_check(args)
        return run_diagrams(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # last-resort guard; exit 3 means a bug in md2xarticle
        print(f"error: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        if getattr(args, "verbose", False):
            traceback.print_exc()
        else:
            command = args.command or "diagrams"
            article = getattr(args, "article", "ARTICLE.md")
            print(f"try:   md2xarticle {command} {article} --verbose", file=sys.stderr)
        return EXIT_INTERNAL
