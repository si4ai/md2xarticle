#!/usr/bin/env python3
"""Role-trailer report for a git commit range.

Each commit in the range should carry a Role: trailer whose value is
one of the allowed desk names. A missing trailer or an unknown role
is a finding. Findings name the kind and the commit, never a person.

This is a visible report, not a merge gate: exits 0 even with
findings. A git failure or bad arguments exits 2.

  python3 tools/role_trailer.py --base REV [--head REV] [--root DIR]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_ROLES = ("builder", "typesetter", "validator")
ROLE_TRAILER_RE = re.compile(r"(?im)^Role:\s*(\S.*?)\s*$")


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(root), *args],
        stderr=subprocess.STDOUT,
    )


def role_values(body: str) -> list[str]:
    return [m.group(1).strip() for m in ROLE_TRAILER_RE.finditer(body or "")]


def scan_range(root: Path, base: str, head: str, roles: set[str]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    revs = _git(root, "rev-list", f"{base}..{head}").decode().split()
    known = {item.casefold() for item in roles}
    for rev in revs:
        body = _git(root, "log", "-1", "--format=%B", rev).decode("utf-8", "replace")
        where = f"git commit {rev[:12]}"
        values = role_values(body)
        if not values:
            findings.append(("missing role trailer", where))
            continue
        if not any(item.casefold() in known for item in values):
            findings.append(("no known role", where))
        for item in values:
            if item.casefold() not in known:
                findings.append(("unknown role", where))
    return findings


def to_markdown(findings: list[tuple[str, str]], base: str, head: str) -> str:
    lines = [f"role-trailer report: {base[:12]}..{head[:12]}", ""]
    if not findings:
        lines.append("no findings.")
        lines.append("")
        return "\n".join(lines)
    lines.append(f"{len(findings)} finding(s):")
    for kind, where in findings:
        lines.append(f"- {kind} in {where}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="report missing or unknown Role: trailers")
    ap.add_argument("--base", required=True, help="diff base revision")
    ap.add_argument("--head", default="HEAD", help="diff head revision")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="git work tree")
    ap.add_argument(
        "--role",
        action="append",
        default=None,
        dest="roles",
        help="allowed role (repeatable); default: builder, typesetter, validator",
    )
    args = ap.parse_args(argv)
    try:
        root = args.root
        base = _git(root, "rev-parse", "--verify", f"{args.base}^{{commit}}").decode().strip()
        head = _git(root, "rev-parse", "--verify", f"{args.head}^{{commit}}").decode().strip()
        roles = set(args.roles) if args.roles else set(DEFAULT_ROLES)
        findings = scan_range(root, base, head, roles)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"role_trailer: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(to_markdown(findings, base, head))
    return 0


if __name__ == "__main__":
    sys.exit(main())
