"""The repo passes the hygiene scanner (tools/hygiene.py), and planted files fail it visibly.

tools/hygiene.py is the one scanner; these tests only drive its CLI.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / "tools" / "hygiene.py"
DENY_ENV = "MD2XARTICLE_HYGIENE_DENYLIST"

# Built from pieces so this file does not trip the scan itself.
PLANTED = {
    "email": "contact: jane.doe" + "@" + "corp-mail.biz",
    "home path": "/ho" + "me/alice/notes.md",
    "secret": "token gh" + "p_" + "Ab3" * 12,
    "pem": "-----BEGIN " + "RSA PRIVATE KEY-----",
}


def scan(root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )


def _env_without_deny() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != DENY_ENV}


def test_repo_is_clean():
    proc = scan(ROOT)  # honours MD2XARTICLE_HYGIENE_DENYLIST when set
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_scanner_selftest_passes():
    proc = scan(ROOT, "--selftest")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_planted_file_fails_visibly(tmp_path):
    for kind, value in PLANTED.items():
        d = tmp_path / kind.replace(" ", "-")
        d.mkdir()
        (d / "planted.txt").write_text(value + "\n", encoding="utf-8")
        proc = scan(d, env=_env_without_deny())
        assert proc.returncode == 1, kind
        assert f"- {kind} in planted.txt" in proc.stdout, (kind, proc.stdout)
        assert value not in proc.stdout + proc.stderr


def test_deny_list_from_env(tmp_path):
    deny = tmp_path / "deny.txt"
    deny.write_text("# names that must never ship\nZorblax Quint\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "doc.md").write_text("Thanks to zorblax quint for the idea.\n", encoding="utf-8")
    proc = scan(repo, env={**_env_without_deny(), DENY_ENV: str(deny)})
    assert proc.returncode == 1
    assert "- deny-list in doc.md" in proc.stdout
    assert "orblax" not in (proc.stdout + proc.stderr).lower()


def test_clean_tree_and_placeholders_pass(tmp_path):
    (tmp_path / "ok.md").write_text(
        "Write to out/images/01.png. Mail someone" + "@" + "example.com. "
        "See /home/<user>/ and C:\\Users\\<user>\\ and /mnt/c/Users/<user>/ shares.\n",
        encoding="utf-8",
    )
    proc = scan(tmp_path, env=_env_without_deny())
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_git_pointer_file_is_not_scanned(tmp_path):
    """A linked worktree stores .git as a file, often with a home-directory path."""
    (tmp_path / ".git").write_text("gitdir: " + "/ho" + "me/runner/work/repo/.git\n", encoding="utf-8")
    (tmp_path / "ok.md").write_text("A clean file.\n", encoding="utf-8")
    proc = scan(tmp_path, env=_env_without_deny())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # A real finding in a normal file is still reported.
    (tmp_path / "notes.md").write_text("/" + "ho" + "me/alice/notes.md\n", encoding="utf-8")
    proc = scan(tmp_path, env=_env_without_deny())
    assert proc.returncode == 1
    assert "- home path in notes.md" in proc.stdout
    assert "- home path in .git" not in proc.stdout


def test_wsl_url_is_clean_doubled_mnt_and_glpat_are_flagged(tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "doc.md").write_text(
        "See https://" + "wsl" + ".localhost/Ubuntu\n", encoding="utf-8"
    )
    proc = scan(clean, env=_env_without_deny())
    assert proc.returncode == 0, proc.stdout + proc.stderr

    dirty = tmp_path / "dirty"
    dirty.mkdir()
    (dirty / "paths.md").write_text(
        "/mnt//c/" + "Users" + "/alice/file\n", encoding="utf-8"
    )
    proc = scan(dirty, env=_env_without_deny())
    assert proc.returncode == 1
    assert "- home path in paths.md" in proc.stdout

    token = "gl" + "pat-" + "Ab3_" * 8
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "keys.md").write_text(f"token {token}\n", encoding="utf-8")
    proc = scan(secrets, env=_env_without_deny())
    assert proc.returncode == 1
    assert "- secret in keys.md" in proc.stdout
    assert token not in proc.stdout + proc.stderr
