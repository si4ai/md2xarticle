#!/usr/bin/env python3
"""Hygiene scan for an open-source repo. Standard library only.

Flags email shapes, home-directory paths, secret shapes, and terms from an
optional deny-list file kept outside the repo (``--deny-list FILE`` or the
``MD2X_DENYLIST`` environment variable). Findings name the kind, file, and
line, never the matched text.

Usage: python tests/hygiene.py [--root DIR] [--deny-list FILE]
Exit codes: 0 clean, 1 findings, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DENYLIST_ENV = ("MD2X_DENYLIST", "MD2XARTICLE_HYGIENE_DENYLIST")
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "out", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".ttf", ".otf", ".woff", ".woff2", ".zip", ".gz", ".whl", ".pyc"}
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")),
    ("home-path", re.compile(r"(?<![\w.])/(?:home|Users)/(?!<)[A-Za-z0-9_][A-Za-z0-9_.-]*")),
    ("home-path", re.compile(r"\b[A-Za-z]:\\{1,2}Users\\{1,2}(?!<)[^\\\s\"'`<>]+", re.IGNORECASE)),
    ("home-path", re.compile(r"\\{2}wsl(?:\$|\.localhost)\\{1,2}[^\\\s\"'`<>]+", re.IGNORECASE)),
    ("secret", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("secret", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("secret", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("secret", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("secret", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("secret", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("secret", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("credential-url", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@'\"<>]+:[^/\s@'\"<>]+@")),
]


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    line: int

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}"


def list_files(root: Path) -> list[Path]:
    """Tracked plus untracked-not-ignored files under git; a plain walk otherwise."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, check=True,
        ).stdout
        if (root / ".git").exists():
            return sorted(root / p for p in out.decode("utf-8").split("\0") if p)
    except (OSError, subprocess.CalledProcessError):
        pass
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        files.extend(Path(dirpath) / f for f in filenames)
    return sorted(files)


def load_denylist(path: Path | None) -> list[re.Pattern[str]]:
    if path is None:
        return []
    terms = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        term = raw.strip()
        if len(term) >= 3 and not term.startswith("#"):
            terms.append(re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE))
    return terms


def scan_text(text: str, rel: str, deny: list[re.Pattern[str]]) -> list[Finding]:
    found = []
    for n, line in enumerate(text.splitlines(), start=1):
        for kind, pat in PATTERNS:
            for m in pat.finditer(line):
                if kind == "email" and m.group(1).lower() in ALLOWED_EMAIL_DOMAINS:
                    continue
                found.append(Finding(kind, rel, n))
                break
        if any(p.search(line) for p in deny):
            found.append(Finding("deny-list", rel, n))
    return found


def scan(root: Path, deny: list[re.Pattern[str]], files: list[Path] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path in files if files is not None else list_files(root):
        rel = path.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if any(p.search(rel) for p in deny):
            findings.append(Finding("deny-list (file name)", rel, 0))
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        findings.extend(scan_text(data.decode("utf-8", errors="replace"), rel, deny))
    return findings


def denylist_from_env() -> Path | None:
    for name in DENYLIST_ENV:
        value = os.environ.get(name)
        if value:
            return Path(value)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--deny-list", type=Path, default=None)
    args = ap.parse_args(argv)
    deny_path = args.deny_list or denylist_from_env()
    try:
        deny = load_denylist(deny_path)
    except OSError:
        print("hygiene: cannot read the deny-list file", file=sys.stderr)
        return 2
    findings = scan(args.root.resolve(), deny)
    for f in findings:
        print(f"hygiene: {f}", file=sys.stderr)
    if findings:
        print(f"hygiene: {len(findings)} finding(s). Matched text is not printed.", file=sys.stderr)
        return 1
    print(f"hygiene: clean{' (with deny-list)' if deny else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
