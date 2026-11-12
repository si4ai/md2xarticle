"""``md2xarticle check ARTICLE.md``: privacy scan only, writes nothing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from md2xarticle.errors import UsageError
from md2xarticle.privacy import (
    findings_as_json,
    format_findings,
    load_deny_list,
    resolve_deny_path,
    scan_text,
)

EXIT_OK, EXIT_FINDINGS = 0, 1


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser(
        "check",
        help="privacy scan only; print findings with line numbers and write nothing",
        description="Scan ARTICLE.md for email, phone, local-path, secret, and deny-list shapes. Writes nothing.",
    )
    add_scan_arguments(p, require_privacy_flag=False)
    return p


def add_scan_arguments(p: argparse.ArgumentParser, *, require_privacy_flag: bool) -> None:
    """Flags shared by ``check`` and ``diagrams --check-privacy``."""
    if require_privacy_flag:
        p.add_argument(
            "--check-privacy",
            action="store_true",
            help="run the privacy scan after writing (output is still written)",
        )
    p.add_argument(
        "--deny-list",
        type=Path,
        default=None,
        metavar="FILE",
        help="optional local deny-list of names (or set MD2XARTICLE_PRIVACY_DENYLIST)",
    )
    if not require_privacy_flag:
        p.add_argument("article", metavar="ARTICLE.md", type=Path)
        p.add_argument("--json", action="store_true", help="print findings as JSON")
        p.add_argument("-v", "--verbose", action="store_true", help="full error details")


def load_deny(flag: Path | None) -> tuple[str, ...]:
    try:
        return load_deny_list(resolve_deny_path(flag))
    except FileNotFoundError as exc:
        raise UsageError(str(exc)) from None


def read_article(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise UsageError(f"file not found: {path}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read {path}: {exc}") from None


def run_check(args: argparse.Namespace) -> int:
    text = read_article(args.article)
    findings = scan_text(text, load_deny(args.deny_list))
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not findings,
                    "privacy_findings": findings_as_json(args.article, findings),
                },
                indent=2,
            )
        )
    else:
        print(format_findings(args.article, findings), end="")
    return EXIT_FINDINGS if findings else EXIT_OK
