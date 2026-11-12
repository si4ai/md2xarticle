"""The repo passes its own hygiene scan, and a planted file fails it visibly."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests import hygiene

ROOT = Path(__file__).resolve().parent.parent
SCANNER = Path(hygiene.__file__)

# Built from pieces so this file does not trip the scan itself.
PLANTED = {
    "email": "contact: jane.doe" + "@" + "corp-mail.test",
    "home-path": "/ho" + "me/alice/notes.md",
    "secret": "token gh" + "p_" + "Ab3" * 12,
    "credential-url": "https://" + "bob:hunter2" + "@" + "git.invalid/repo",
}


def test_repo_is_clean():
    deny = hygiene.load_denylist(hygiene.denylist_from_env())
    findings = hygiene.scan(ROOT, deny)
    assert not findings, "\n".join(map(str, findings))


def test_planted_file_fails_visibly(tmp_path):
    lines = list(PLANTED.values()) + [
        "C:" + "\\Users\\alice\\out",
        "\\\\" + "wsl$\\Ubuntu\\home",
        "-----BEGIN " + "RSA PRIVATE KEY-----",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "Authorization: Bearer " + "x" * 32,
    ]
    (tmp_path / "planted.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(tmp_path)], capture_output=True, text=True
    )
    assert proc.returncode == 1
    for kind in ("email", "home-path", "secret", "credential-url"):
        assert f": {kind}" in proc.stderr, kind
    # Every planted line is reported (a line may match more than one kind).
    reported = {int(ln.split(":")[2]) for ln in proc.stderr.splitlines() if "planted.txt:" in ln}
    assert reported == set(range(1, len(lines) + 1))
    for value in PLANTED.values():
        assert value not in proc.stderr and value not in proc.stdout


def test_deny_list_from_env(tmp_path, monkeypatch):
    deny = tmp_path.parent / f"{tmp_path.name}-deny.txt"
    deny.write_text("# names that must never ship\nZorblax Quint\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "doc.md").write_text("Thanks to zorblax quint for the idea.\n", encoding="utf-8")
    monkeypatch.setenv("MD2X_DENYLIST", str(deny))
    proc = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(repo)], capture_output=True, text=True
    )
    assert proc.returncode == 1
    assert "doc.md:1: deny-list" in proc.stderr
    assert "orblax" not in proc.stderr.lower()


def test_clean_tree_and_placeholders_pass(tmp_path):
    (tmp_path / "ok.md").write_text(
        "Write to out/images/01.png. Mail someone" + "@" + "example.com. "
        "See /home/<user>/ and C:\\Users\\<user>\\ and \\\\wsl$ shares.\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(tmp_path)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
