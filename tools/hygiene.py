#!/usr/bin/env python3
"""Repo hygiene scanner. Standard library only.

Scans the work tree for email shapes, home-directory paths (Windows
user folders, Unix and macOS home folders, WSL UNC shares, and
Windows user folders seen from WSL under /mnt),
secret shapes, PEM blocks, typographic marks, and byte-order marks.
Typographic marks under tests/snapshots/ are allowed so fixtures
can keep the HTML writer's typography (for example the en dash
used when nested lists are flattened).
An optional deny-list file kept outside the repo may be passed with
--deny-list. --staged scans index blobs the same way.

The planted fixture under tools/testdata/ is excluded from a normal
scan. --selftest runs the scanner against that fixture and exits 0
only when the expected kinds are reported, so a finding is proven
to fail visibly.

Findings name the kind and the path (or commit), never the matched
text.

Exit codes: 0 clean (or a successful self-test), 1 findings (or a
failed self-test), 2 usage or internal error.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PLANT_REL = Path("tools") / "testdata" / "hygiene_plant.txt"
SNAPSHOTS_PREFIX = "tests/snapshots/"
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "dist",
    }
)
SKIP_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".zip",
        ".gz",
        ".bz2",
        ".xz",
        ".whl",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".pyc",
        ".pyo",
        ".pyd",
    }
)
MAX_BYTES = 2_000_000
_BOM_PREFIXES = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")
_TEXT_MARKS = frozenset(
    {
        0x00A0,
        0x00B1,
        0x00B7,
        0x0394,
        0x200B,
        0x200C,
        0x200D,
        0x2013,
        0x2014,
        0x2018,
        0x2019,
        0x201C,
        0x201D,
        0x2026,
        0x2190,
        0x2191,
        0x2192,
        0x2193,
        0x2264,
        0x2713,
        0xFEFF,
    }
)

# Placeholder local-part/domain values that docs are allowed to use.
_PLACEHOLDER_EMAIL_DOMAINS = frozenset(
    {
        "example.com",
        "example.org",
        "example.net",
        "users.noreply.github.com",
        "noreply.github.com",
        "users.noreply.gitlab.com",
        "noreply.gitlab.com",
    }
)
_PLACEHOLDER_EMAIL_TLDS = frozenset({"example", "test", "invalid", "localhost"})
# File-extension "domains" from Markdown image/asset refs, not mail.
_ASSET_TLDS = frozenset(
    {
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "webp",
        "ico",
        "js",
        "mjs",
        "css",
        "py",
        "md",
        "txt",
        "json",
        "whl",
        "gz",
    }
)
_HOME_PLACEHOLDERS = frozenset(
    {
        "",
        "*",
        "...",
        "example",
        "user",
        "username",
        "you",
        "name",
        "folder",
        "someone",
        "shared",
        "default",
        "public",
        "all users",
    }
)

# Literals below are assembled from pieces so this source file does not
# itself match the rules it enforces.
_USERS = "Users"
_HOME = "home"
_WSL = "wsl"
_PRIV = "PRIVATE "
_KEY = "KEY"

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
_WIN_USERS_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:|\\\\[?]\\[A-Za-z]:)(?:\\\\|\\|/)+"
    + _USERS
    + r"(?:\\\\|\\|/)+([^\\/\s\"'`<>()\[\]{}:;,|]*)",
    re.IGNORECASE,
)
_POSIX_HOME_RE = re.compile(
    r"(?<![\w.~-])/(?:" + _HOME + r"|" + _USERS + r")/"
    r"([^\\/\s\"'`<>()\[\]{}:;,|]*)"
)
# WSL UNC shares: the legacy wsl$ host and the current wsl.localhost
# host, written with backslashes or forward slashes.
_WSL_RE = re.compile(
    r"(?:\\\\|//)" + _WSL + r"(?:\$|\.localhost)[\\/]+\S+",
    re.IGNORECASE,
)
# Windows user folders seen from inside WSL: /mnt/<drive>/Users/<name>.
_WSL_MNT_RE = re.compile(
    r"(?<![\w.~-])/mnt/[A-Za-z]/" + _USERS + r"/([^\\/\s\"'`<>()\[\]{}:;,|]*)",
    re.IGNORECASE,
)
_PEM_RE = re.compile(
    r"-{5}BEGIN [A-Z0-9 ]{0,40}" + _PRIV + _KEY + r"-{5}"
)
_AWS_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Za-z0-9_-])"
)
_GITHUB_PAT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github" + r"_pat_[A-Za-z0-9_]{20,})(?![A-Za-z0-9_-])"
)
_PYPI_RE = re.compile(
    r"(?<![A-Za-z0-9_-])pypi-AgE[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"
)
_SLACK_RE = re.compile(
    r"(?<![A-Za-z0-9_-])xox[abprs]-[A-Za-z0-9-]{10,}(?![A-Za-z0-9_-])"
)
# sk- API keys (OpenAI and Anthropic shapes). The body must be at least
# 32 characters and carry a digit, so kebab-case slugs do not match.
_SK_RE = re.compile(
    r"(?<![A-Za-z0-9_-])sk-(?:proj-|ant-[a-z0-9]{2,8}-|svcacct-|admin-)?"
    r"(?=[A-Za-z_-]*[0-9])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_-])"
)
_URL_CRED_RE = re.compile(r"://[^\s/@:]+:[^\s/@]+@")


def email_is_placeholder(addr: str) -> bool:
    local, _, domain = addr.rpartition("@")
    domain = domain.casefold().rstrip(".")
    if local == "git":
        return True
    if domain in _PLACEHOLDER_EMAIL_DOMAINS:
        return True
    if any(domain.endswith("." + item) for item in _PLACEHOLDER_EMAIL_DOMAINS):
        return True
    tld = domain.rsplit(".", 1)[-1]
    return tld in _PLACEHOLDER_EMAIL_TLDS or tld in _ASSET_TLDS


def home_segment_is_placeholder(segment: str) -> bool:
    seg = segment.strip().casefold()
    if seg in _HOME_PLACEHOLDERS:
        return True
    return seg[:1] in ("$", "%", "<", "{", "*", ".")


def scan_text(text: str, deny: tuple[str, ...]) -> list[str]:
    """Return finding kinds present in text. Never returns the match."""
    kinds: list[str] = []
    seen: set[str] = set()

    def add(kind: str) -> None:
        if kind not in seen:
            seen.add(kind)
            kinds.append(kind)

    for match in EMAIL_RE.finditer(text):
        if not email_is_placeholder(match.group(1)):
            add("email")
            break
    if any(
        not home_segment_is_placeholder(match.group(1))
        for match in _WIN_USERS_RE.finditer(text)
    ) or any(
        not home_segment_is_placeholder(match.group(1))
        for match in _POSIX_HOME_RE.finditer(text)
    ) or any(
        not home_segment_is_placeholder(match.group(1))
        for match in _WSL_MNT_RE.finditer(text)
    ) or _WSL_RE.search(text):
        add("home path")
    if _PEM_RE.search(text):
        add("pem")
    if (
        _AWS_ID_RE.search(text)
        or _GITHUB_PAT_RE.search(text)
        or _PYPI_RE.search(text)
        or _SLACK_RE.search(text)
        or _SK_RE.search(text)
        or _URL_CRED_RE.search(text)
    ):
        add("secret")
    folded = text.casefold()
    for word in deny:
        if word and word in folded:
            add("deny-list")
            break
    mark = text_mark(text)
    if mark is not None:
        add(f"typographic mark U+{mark:04X}")
    return kinds


def text_mark(text: str) -> int | None:
    if not text:
        return None
    for ch in text:
        point = ord(ch)
        if point in _TEXT_MARKS:
            return point
    return None


def blob_has_bom(data: bytes) -> bool:
    return bool(data) and data.startswith(_BOM_PREFIXES)


def kinds_in_blob(data: bytes, deny: tuple[str, ...]) -> list[str]:
    kinds: list[str] = []
    if blob_has_bom(data):
        kinds.append("byte-order mark")
    if not data or len(data) > MAX_BYTES or b"\0" in data[:8192]:
        return kinds
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return kinds
    kinds.extend(scan_text(text, deny))
    return kinds


def load_deny_list(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    if not path.is_file():
        raise FileNotFoundError(f"deny-list not found: {path}")
    words: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        words.append(line.casefold())
    return tuple(words)


def iter_files(root: Path, excluded: set[Path]):
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in SKIP_DIR_NAMES and not name.endswith(".egg-info")
        ]
        for name in filenames:
            if name in SKIP_DIR_NAMES:
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in excluded:
                continue
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            yield resolved


def read_text(path: Path) -> str | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_BYTES or size == 0:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def rel_where(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def allow_typographic(where: str) -> bool:
    return where.replace("\\", "/").startswith(SNAPSHOTS_PREFIX)


def scan_tree(
    root: Path, deny: tuple[str, ...], excluded: set[Path]
) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in iter_files(root, excluded):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if not data:
            continue
        where = rel_where(path, root)
        for kind in kinds_in_blob(data, deny):
            if allow_typographic(where) and kind.startswith("typographic mark"):
                continue
            findings.append((kind, where))
    return findings


def scan_staged(
    root: Path, deny: tuple[str, ...], excluded: set[Path]
) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    raw = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z")
    for rel in raw.decode("utf-8", "replace").split("\0"):
        if not rel:
            continue
        resolved = (root / rel).resolve()
        if resolved in excluded:
            continue
        try:
            data = _git(root, "show", f":{rel}")
        except subprocess.CalledProcessError as exc:
            raise OSError(f"cannot read staged blob {rel}: {exc}") from exc
        if not data:
            continue
        for kind in kinds_in_blob(data, deny):
            where = rel.replace("\\", "/")
            if allow_typographic(where) and kind.startswith("typographic mark"):
                continue
            findings.append((kind, where))
    return findings


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(root), *args],
        stderr=subprocess.STDOUT,
    )


def scan_commits(
    root: Path, base: str, head: str, deny: tuple[str, ...]
) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    revs = (
        _git(root, "rev-list", f"{base}..{head}")
        .decode()
        .split()
    )
    for rev in revs:
        body = _git(root, "log", "-1", "--format=%B", rev).decode(
            "utf-8", "replace"
        )
        where = f"git commit {rev[:12]}"
        for kind in scan_text(body, deny):
            findings.append((kind, where))
    return findings


def default_excluded(root: Path) -> set[Path]:
    plant = (root / PLANT_REL).resolve()
    return {plant} if plant.exists() else set()


def to_markdown(findings: list[tuple[str, str]]) -> str:
    if not findings:
        return "hygiene: no findings.\n"
    lines = [f"hygiene: {len(findings)} finding(s)", ""]
    for kind, where in findings:
        lines.append(f"- {kind} in {where}")
    lines.append("")
    return "\n".join(lines)


# Each planted form, keyed by its label in the fixture, and the kind it
# must report. A form is the labelled line plus any lines up to the next
# blank line, so a multi-line PEM block counts as one form.
PLANT_FORMS: dict[str, str] = {
    "email": "email",
    "windows home": "home path",
    "posix home": "home path",
    "macos home": "home path",
    "wsl share": "home path",
    "wsl share forward slashes": "home path",
    "wsl localhost share": "home path",
    "wsl localhost share forward slashes": "home path",
    "wsl mnt windows home": "home path",
    "pem": "pem",
    "github token shape": "secret",
    "aws key shape": "secret",
    "pypi token shape": "secret",
    "sk key shape": "secret",
    "sk project key shape": "secret",
}
# Labels starting with this prefix are near misses that must stay clean.
PLANT_CLEAN_PREFIX = "clean "


def plant_forms(text: str) -> dict[str, str]:
    """Map each label in the fixture to the text of its form."""
    forms: dict[str, str] = {}
    label: str | None = None
    lines: list[str] = []
    for raw in text.splitlines() + [""]:
        if not raw.strip():
            if label is not None:
                forms[label] = "\n".join(lines)
            label, lines = None, []
            continue
        if label is None:
            head, sep, _ = raw.partition(":")
            if not sep:
                continue
            label = head.strip()
        lines.append(raw)
    return forms


def run_selftest(root: Path) -> int:
    plant = (root / PLANT_REL).resolve()
    if not plant.is_file():
        print(f"hygiene self-test: planted fixture missing: {PLANT_REL}", file=sys.stderr)
        return 2
    text = read_text(plant)
    if text is None:
        print("hygiene self-test: planted fixture could not be read", file=sys.stderr)
        return 2
    forms = plant_forms(text)
    failures: list[str] = []
    for label, kind in PLANT_FORMS.items():
        if label not in forms:
            failures.append(f"form missing from fixture: {label}")
        elif kind not in scan_text(forms[label], ()):
            failures.append(f"form not reported as {kind}: {label}")
    clean = [label for label in forms if label.startswith(PLANT_CLEAN_PREFIX)]
    for label in clean:
        kinds = scan_text(forms[label], ())
        if kinds:
            failures.append(
                f"near miss reported as {', '.join(kinds)}: {label}"
            )
    if failures:
        print("hygiene self-test failed:", file=sys.stderr)
        for line in failures:
            print(f"- {line}", file=sys.stderr)
        return 1
    print(
        f"hygiene self-test ok: {len(PLANT_FORMS)} planted forms reported, "
        f"{len(clean)} near misses clean."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scan the tree for hygiene findings")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="work tree to scan")
    ap.add_argument(
        "--deny-list",
        type=Path,
        default=None,
        help="optional deny-list file kept outside the repo",
    )
    ap.add_argument(
        "--base",
        default=None,
        help="with --head, also scan commit messages in BASE..HEAD",
    )
    ap.add_argument("--head", default="HEAD", help="range head for --base")
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="prove the planted fixture fails visibly, then exit",
    )
    ap.add_argument(
        "--staged",
        action="store_true",
        help="scan staged index blobs instead of the work tree",
    )
    args = ap.parse_args(argv)
    root = args.root
    try:
        deny_path = args.deny_list
        if deny_path is None and os.environ.get("MD2XARTICLE_HYGIENE_DENYLIST"):
            deny_path = Path(os.environ["MD2XARTICLE_HYGIENE_DENYLIST"])
        deny = load_deny_list(deny_path)
        if args.selftest:
            return run_selftest(root)
        excluded = default_excluded(root)
        if args.staged:
            findings = scan_staged(root, deny, excluded)
        else:
            findings = scan_tree(root, deny, excluded)
        if args.base:
            findings.extend(scan_commits(root, args.base, args.head, deny))
    except FileNotFoundError as exc:
        print(f"hygiene: {exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"hygiene: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(to_markdown(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
