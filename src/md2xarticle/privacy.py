"""Privacy scan for an article: findings with file and line, no edits.

Flags email and phone shapes, local home-directory paths, secret shapes
(API keys, bearer tokens, PEM blocks, credentials in URLs), and names
from an optional local deny-list. Findings name the kind and the line,
never the matched text.

The optional deny-list path comes from --deny-list or the
MD2XARTICLE_PRIVACY_DENYLIST environment variable. That file is never
shipped with the package.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

DENY_ENV = "MD2XARTICLE_PRIVACY_DENYLIST"

# Placeholder local-part/domain values that docs and examples may use.
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
        "html",
        "toml",
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

# Path, email, PEM, and key patterns match tools/hygiene.py. Literals in
# that block are assembled from pieces so this source does not itself
# match the rules it enforces. Phone and bearer patterns are extra.
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
# host, written with backslashes or forward slashes. The "//wsl" form
# is a share, not a URL: a lookbehind skips https://wsl.localhost/...
_WSL_RE = re.compile(
    r"(?:\\\\|(?<!:)//)" + _WSL + r"(?:\$|\.localhost)[\\/]+\S+",
    re.IGNORECASE,
)
# Windows user folders seen from inside WSL: /mnt/<drive>/Users/<name>.
_WSL_MNT_RE = re.compile(
    r"(?<![\w.~-])/mnt/+[A-Za-z]/+" + _USERS + r"/+([^\\/\s\"'`<>()\[\]{}:;,|]*)",
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
_GITLAB_PAT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])" + "gl" + "pat-"
    r"[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"
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

# Formatted North American numbers, with separators so dates, versions,
# sizes, and IPs do not match.
_PHONE_NA_RE = re.compile(
    r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4})(?!\d)"
)
# International: a +country code, then grouped digits with separators.
_PHONE_INTL_RE = re.compile(
    r"(?<!\w)\+[1-9]\d{0,2}(?:[\s.-]\(?\d{1,4}\)?)(?:[\s.-]\d{2,4}){1,3}(?!\d)"
)
_BEARER_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])Bearer\s+[A-Za-z0-9._\-+=/]{16,}(?![A-Za-z0-9._\-+=/])"
)


@dataclass(frozen=True)
class Finding:
    line: int
    kind: str


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


def _kinds_on_line(line: str, deny: tuple[str, ...]) -> list[str]:
    kinds: list[str] = []
    seen: set[str] = set()

    def add(kind: str) -> None:
        if kind not in seen:
            seen.add(kind)
            kinds.append(kind)

    for match in EMAIL_RE.finditer(line):
        if not email_is_placeholder(match.group(1)):
            add("email")
            break
    if _PHONE_NA_RE.search(line) or _PHONE_INTL_RE.search(line):
        add("phone")
    if any(
        not home_segment_is_placeholder(match.group(1))
        for match in _WIN_USERS_RE.finditer(line)
    ) or any(
        not home_segment_is_placeholder(match.group(1))
        for match in _POSIX_HOME_RE.finditer(line)
    ) or any(
        not home_segment_is_placeholder(match.group(1))
        for match in _WSL_MNT_RE.finditer(line)
    ) or _WSL_RE.search(line):
        add("home path")
    if (
        _PEM_RE.search(line)
        or _AWS_ID_RE.search(line)
        or _GITHUB_PAT_RE.search(line)
        or _GITLAB_PAT_RE.search(line)
        or _PYPI_RE.search(line)
        or _SLACK_RE.search(line)
        or _SK_RE.search(line)
        or _URL_CRED_RE.search(line)
        or _BEARER_RE.search(line)
    ):
        add("secret")
    folded = line.casefold()
    for word in deny:
        if word and word in folded:
            add("deny-list")
            break
    return kinds


def scan_text(text: str, deny: tuple[str, ...] = ()) -> list[Finding]:
    """Return findings in line order. Never includes the matched text."""
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for kind in _kinds_on_line(line, deny):
            findings.append(Finding(line=number, kind=kind))
    return findings


def resolve_deny_path(flag: Path | None = None) -> Path | None:
    """Flag wins over MD2XARTICLE_PRIVACY_DENYLIST; neither means no list."""
    if flag is not None:
        return flag
    env = os.environ.get(DENY_ENV)
    if env:
        return Path(env)
    return None


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


def format_findings(source: Path | str, findings: list[Finding]) -> str:
    where = source if isinstance(source, str) else source.as_posix()
    if not findings:
        return "privacy: no findings.\n"
    lines = [f"{where}:{item.line}: {item.kind}" for item in findings]
    lines.append("")
    return "\n".join(lines)


def findings_as_json(source: Path | str, findings: list[Finding]) -> list[dict]:
    where = source if isinstance(source, str) else source.as_posix()
    return [{"file": where, "line": item.line, "kind": item.kind} for item in findings]
