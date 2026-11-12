"""CLI for ``md2xarticle check`` and ``diagrams --check-privacy``."""
from __future__ import annotations

import json
from pathlib import Path

from md2xarticle import cli
from md2xarticle.privacy import DENY_ENV

# Built from pieces so this file does not trip the repo hygiene scan.
EMAIL = "jane.doe" + "@" + "corp-mail.biz"
DENY_NAME = "Zorblax Quint"

CLEAN_MD = """# Title

A short article. Write images to out/images/01.png.

```mermaid
flowchart LR
    A[Start] --> B[End]
```
"""


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = cli.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_check_clean_article_exits_0_and_writes_nothing(capsys, tmp_path):
    md = tmp_path / "article.md"
    md.write_text(CLEAN_MD, encoding="utf-8")
    before = {p.name for p in tmp_path.iterdir()}
    code, out, err = run(capsys, "check", str(md))
    assert code == 0, err
    assert out == "privacy: no findings.\n"
    assert {p.name for p in tmp_path.iterdir()} == before


def test_check_prints_findings_with_line_and_exits_1(capsys, tmp_path):
    md = tmp_path / "article.md"
    md.write_text(f"# Title\n\nMail {EMAIL}.\n", encoding="utf-8")
    code, out, err = run(capsys, "check", str(md))
    assert code == 1
    assert out == f"{md.as_posix()}:3: email\n"
    assert EMAIL not in out + err


def test_check_json_and_missing_file(capsys, tmp_path):
    md = tmp_path / "article.md"
    md.write_text(f"Mail {EMAIL}.\n", encoding="utf-8")
    code, out, err = run(capsys, "check", str(md), "--json")
    assert code == 1, err
    data = json.loads(out)
    assert data["ok"] is False
    assert data["privacy_findings"] == [
        {"file": md.as_posix(), "line": 1, "kind": "email"}
    ]
    assert EMAIL not in out
    missing = tmp_path / "missing.md"
    code, _, err = run(capsys, "check", str(missing))
    assert code == 2 and "file not found" in err


def test_check_deny_list_flag_and_env(capsys, tmp_path, monkeypatch):
    md = tmp_path / "article.md"
    md.write_text(f"Thanks to {DENY_NAME}.\n", encoding="utf-8")
    deny = tmp_path / "deny.txt"
    deny.write_text("# local names\nZorblax Quint\n", encoding="utf-8")
    monkeypatch.delenv(DENY_ENV, raising=False)
    code, out, err = run(capsys, "check", str(md))
    assert code == 0, err
    code, out, err = run(capsys, "check", str(md), "--deny-list", str(deny))
    assert code == 1
    assert out == f"{md.as_posix()}:1: deny-list\n"
    assert "orblax" not in (out + err).lower()
    monkeypatch.setenv(DENY_ENV, str(deny))
    code, out, err = run(capsys, "check", str(md))
    assert code == 1 and "deny-list" in out
    code, _, err = run(capsys, "check", str(md), "--deny-list", str(tmp_path / "nope.txt"))
    assert code == 2 and "deny-list not found" in err


def test_diagrams_check_privacy_still_writes_and_exits_1(capsys, tmp_path):
    md = tmp_path / "article.md"
    md.write_text(CLEAN_MD.replace("A short article.", f"Mail {EMAIL}."), encoding="utf-8")
    out_dir = tmp_path / "out"
    code, out, err = run(
        capsys, "diagrams", str(md), "-o", str(out_dir), "--check-privacy", "--json"
    )
    assert code == 1, err
    assert (out_dir / "images" / "01.png").is_file()
    data = json.loads(out)
    assert data["ok"] is False
    assert data["privacy_findings"] == [
        {"file": md.as_posix(), "line": 3, "kind": "email"}
    ]
    assert EMAIL not in out + err
    # Without the flag, the same article converts cleanly and omits the key.
    clean_out = tmp_path / "clean"
    code, out, err = run(capsys, "diagrams", str(md), "-o", str(clean_out), "--json")
    assert code == 0, err
    data = json.loads(out)
    assert data["ok"] is True
    assert "privacy_findings" not in data
    assert (clean_out / "images" / "01.png").is_file()


def test_check_appears_in_help():
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "md2xarticle", "check", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    for flag in ("--deny-list", "--json"):
        assert flag in proc.stdout
    proc = subprocess.run(
        [sys.executable, "-m", "md2xarticle", "diagrams", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--check-privacy" in proc.stdout
    assert "--deny-list" in proc.stdout
