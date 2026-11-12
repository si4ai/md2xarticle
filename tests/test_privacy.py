"""Product privacy scanner (md2xarticle.privacy).

Planted values are built at runtime so the repo hygiene scan does not
flag this file. Path and secret *shapes* already covered by
tools/hygiene.py are sampled here, not re-enumerated; phone, bearer,
line numbers, and negative cases for article text are the extra checks.
"""
from __future__ import annotations

from pathlib import Path

from md2xarticle.privacy import (
    DENY_ENV,
    Finding,
    format_findings,
    load_deny_list,
    resolve_deny_path,
    scan_text,
)

# Built from pieces so this file does not trip the repo hygiene scan.
EMAIL = "jane.doe" + "@" + "corp-mail.biz"
PHONE = "(" + "555" + ") " + "010" + "-" + "0100"
PHONE_DASH = "555" + "-" + "010" + "-" + "0100"
PHONE_INTL = "+" + "44" + " 20 " + "7946" + " " + "0958"
POSIX_HOME = "/" + "ho" + "me" + "/alice/notes.md"
WIN_HOME = "C:\\" + "Users" + "\\alice\\file.txt"
MNT_HOME = "/mnt/c/" + "Users" + "/alice/file"
WSL_SHARE = "\\\\" + "wsl" + "$" + "\\Ubuntu\\home\\alice"
PEM = "-----BEGIN " + "RSA PRIVATE KEY-----"
GITHUB_TOKEN = "gh" + "p_" + "Ab3" * 12
BEARER = "Bear" + "er " + "aA1_" * 8
URL_CRED = "https://user:" + "s3cret" + "@192.168.0.1/repo.git"
DENY_NAME = "Zorblax Quint"


def kinds(text: str, deny: tuple[str, ...] = ()) -> list[tuple[int, str]]:
    return [(item.line, item.kind) for item in scan_text(text, deny)]


def test_flags_each_kind_with_line_numbers():
    article = "\n".join(
        [
            "# Title",
            f"Mail {EMAIL}.",
            f"Call {PHONE} or {PHONE_DASH} or {PHONE_INTL}.",
            f"Path {POSIX_HOME}",
            f"Path {WIN_HOME}",
            f"Path {MNT_HOME}",
            f"Path {WSL_SHARE}",
            f"Key {GITHUB_TOKEN}",
            PEM,
            f"Header {BEARER}",
            f"Clone {URL_CRED}",
            f"Thanks to {DENY_NAME}.",
            "",
        ]
    )
    deny = (DENY_NAME.casefold(),)
    got = kinds(article, deny)
    assert got == [
        (2, "email"),
        (3, "phone"),
        (4, "home path"),
        (5, "home path"),
        (6, "home path"),
        (7, "home path"),
        (8, "secret"),
        (9, "secret"),
        (10, "secret"),
        (11, "secret"),
        (12, "deny-list"),
    ]


def test_findings_text_names_file_and_line_not_the_match():
    findings = scan_text(f"Mail {EMAIL}.\n", ())
    text = format_findings("article.md", findings)
    assert text == "article.md:1: email\n"
    assert EMAIL not in text
    assert format_findings("article.md", []) == "privacy: no findings.\n"


def test_no_false_positive_on_example_paths_urls_or_code():
    clean = "\n".join(
        [
            "Write to out/ and images/01.png.",
            "See https://example.com/users/alice and https://github.com/org/repo.",
            "Mail someone" + "@" + "example.com.",
            "See /home/<user>/ and C:\\Users\\<user>\\ and /mnt/c/Users/<user>/ shares.",
            "Set token = 'redacted'; a short sk-test is not a key; Bearer token docs.",
            "Body size 1600x900, cover 1500x600, 5:2, 0.65x, 320 px.",
            "Dated 2026-11-12, Python 3.11 to 3.13, mermaidx==0.11.3, line 88.",
            "Hosts 127.0.0.1 and 192.168.0.1 are fine.",
            "```mermaid",
            "flowchart LR",
            "    A[Start] --> B[End]",
            "```",
            "",
        ]
    )
    assert scan_text(clean, ()) == []


def test_deny_list_loader_skips_comments_and_blanks(tmp_path: Path):
    path = tmp_path / "deny.txt"
    path.write_text("# names that must never ship\n\nZorblax Quint\n", encoding="utf-8")
    assert load_deny_list(path) == ("zorblax quint",)
    assert load_deny_list(None) == ()


def test_resolve_deny_path_flag_wins_over_env(tmp_path: Path, monkeypatch):
    flag = tmp_path / "flag.txt"
    env = tmp_path / "env.txt"
    flag.write_text("from-flag\n", encoding="utf-8")
    env.write_text("from-env\n", encoding="utf-8")
    monkeypatch.delenv(DENY_ENV, raising=False)
    assert resolve_deny_path(None) is None
    monkeypatch.setenv(DENY_ENV, str(env))
    assert resolve_deny_path(None) == env
    assert resolve_deny_path(flag) == flag


def test_finding_is_comparable():
    assert Finding(line=1, kind="email") == Finding(line=1, kind="email")
