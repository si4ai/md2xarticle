"""CLI: ``md2xarticle outline ARTICLE.md``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from md2xarticle import cli
from tests.helpers import FIXTURE_MD

SAMPLE_MD = """\
# Article title

## Introduction

## How it works

### The parser

### The renderer

#### Theme details

## Results
"""

SAMPLE_OUTLINE = """\
Outline (X levels)
  H   Introduction
  H   How it works
  SH    The parser
  SH    The renderer
          [bold lead-in] Theme details
  H   Results
"""


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = cli.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def write_md(tmp_path: Path, text: str, name: str = "article.md") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_outline_matches_readme_sample(capsys, tmp_path):
    path = write_md(tmp_path, SAMPLE_MD)
    code, out, err = run(capsys, "outline", str(path))
    assert code == 0, err
    assert out == SAMPLE_OUTLINE
    assert err == ""


def test_empty_article_prints_header_only(capsys, tmp_path):
    path = write_md(tmp_path, "")
    code, out, err = run(capsys, "outline", str(path))
    assert code == 0, err
    assert out == "Outline (X levels)\n"
    assert err == ""


def test_missing_article_exits_2(capsys, tmp_path):
    code, _, err = run(capsys, "outline", str(tmp_path / "missing.md"))
    assert code == 2
    assert "file not found" in err


def test_heading_map_override(capsys, tmp_path):
    path = write_md(tmp_path, "# Title\n\n## Section\n\n# Extra\n")
    code, out, err = run(capsys, "outline", str(path), "--heading-map", "flat")
    assert code == 0, err
    assert out == (
        "Outline (X levels)\n"
        "  H   Section\n"
        "  H   Extra\n"
    )
    assert err == ""


def test_forced_fallback_exits_1_and_still_prints(capsys, tmp_path):
    path = write_md(tmp_path, "# Title\n\n## Section\n\n# Leftover\n")
    code, out, err = run(capsys, "outline", str(path), "--heading-map", "shifted")
    assert code == 1
    assert out == (
        "Outline (X levels)\n"
        "  H   Section\n"
        "  H   Leftover\n"
    )
    assert "no row in the shifted mapping" in err
    assert "Leftover" in err
    assert f"try:   md2xarticle outline {path} --heading-map flat" in err


def test_bad_heading_map_exits_2(capsys, tmp_path):
    path = write_md(tmp_path, "# Title\n")
    with pytest.raises(SystemExit) as info:
        code = cli.main(["outline", str(path), "--heading-map", "mystery"])
        raise SystemExit(code)
    assert info.value.code == 2


def test_synthetic_fixture_outline(capsys):
    # Front matter title plus a "#" heading: the "#" is omitted; ## are Headings.
    code, out, err = run(capsys, "outline", str(FIXTURE_MD))
    assert code == 0, err
    assert out == (
        "Outline (X levels)\n"
        "  H   Overview\n"
        "  H   Decisions\n"
        "  H   Calls\n"
        "  H   Types\n"
        "  H   Broken on purpose\n"
    )
    assert err == ""


def test_outline_does_not_write_files(capsys, tmp_path):
    path = write_md(tmp_path, SAMPLE_MD)
    code, _, err = run(capsys, "outline", str(path))
    assert code == 0, err
    written = [p for p in tmp_path.iterdir() if p != path]
    assert written == []


def test_module_entry_point_help():
    proc = subprocess.run(
        [sys.executable, "-m", "md2xarticle", "outline", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0
    assert "--heading-map" in proc.stdout
    assert "auto" in proc.stdout
    assert "shifted" in proc.stdout
    assert "flat" in proc.stdout


def test_diagrams_still_works_alongside_outline(capsys, tmp_path):
    md = write_md(tmp_path, "", name="empty.md")
    code, out, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "o"), "--json")
    assert code == 0, err
    assert json.loads(out)["images"] == []
