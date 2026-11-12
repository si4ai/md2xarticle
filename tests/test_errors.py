"""Output-contract error paths: ``error:`` then ``try:`` / ``or:``, exit 0/1/2/3."""

from __future__ import annotations

from pathlib import Path

from md2xarticle import cli, factory
from md2xarticle.errors import format_error
from md2xarticle.theme import BUILTIN_THEMES, DEFAULT_THEME

INVALID = """# Title

```mermaid
flowchart TD
  this is not valid((((
```
"""


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = cli.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def _article(tmp_path: Path, text: str = "# Title\n\nHello.\n") -> Path:
    path = tmp_path / "article.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_format_error_layout():
    text = format_error("boom", try_cmd="do this", or_cmd="or that")
    assert text.splitlines() == ["error: boom", "try:   do this", "or:    or that"]


def test_failed_diagram_retry(capsys, tmp_path):
    md = _article(tmp_path, INVALID)
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"))
    assert code == 1
    assert "error: diagram 01 (article.md line " in err
    assert "failed to render:" in err
    assert f"try:   md2xarticle diagrams {md} --only 1 --verbose" in err
    assert "Traceback" not in err


def test_unknown_renderer(capsys, tmp_path):
    md = _article(tmp_path)
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--renderer", "nope")
    assert code == 2
    assert "error: unknown renderer 'nope'" in err
    assert "mermaidx" in err and "mmdc" in err and "mmdr" in err
    assert f"try:   md2xarticle diagrams {md} --renderer mermaidx" in err


def test_unavailable_planned_renderer(capsys, tmp_path):
    md = _article(tmp_path)
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--renderer", "mmdc")
    assert code == 2
    assert "error: renderer 'mmdc' is not installed" in err
    assert 'try:   pip install "md2xarticle[mmdc]"   (needs Node and Chromium)' in err
    assert f"or:    md2xarticle diagrams {md} --renderer mermaidx" in err


def test_unavailable_default_renderer(capsys, tmp_path, monkeypatch):
    md = _article(tmp_path)

    def missing(self) -> bool:
        return False

    monkeypatch.setattr(factory.RENDERERS["mermaidx"], "available", missing)
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"))
    assert code == 2
    assert "error: renderer 'mermaidx' is not installed" in err
    assert "try:   pip install md2xarticle" in err
    assert f"or:    md2xarticle diagrams {md} --renderer mermaidx" in err


def test_missing_input_file(capsys, tmp_path):
    missing = tmp_path / "article.md"
    code, _, err = run(capsys, "diagrams", str(missing), "-o", str(tmp_path / "out"))
    assert code == 2
    assert f"error: file not found: {missing}" in err
    assert f"try:   md2xarticle diagrams {missing}" in err


def test_bad_size_ratio(capsys, tmp_path):
    md = _article(tmp_path)
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--size", "1000x1000")
    assert code == 2
    assert "error: --size must be 16:9 for now, got '1000x1000'" in err
    assert f"try:   md2xarticle diagrams {md} --size 1600x900" in err


def test_bad_size_syntax(capsys, tmp_path):
    md = _article(tmp_path)
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--size", "big")
    assert code == 2
    assert "error: --size must look like WxH, got 'big'" in err
    assert f"try:   md2xarticle diagrams {md} --size 1600x900" in err


def test_missing_custom_path(capsys, tmp_path):
    md = _article(tmp_path)
    custom = tmp_path / "article.toml"
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--custom-path", str(custom))
    assert code == 2
    assert "error: customization file not found:" in err
    assert f"try:   md2xarticle diagrams {md} --custom-path {custom}" in err


def test_invalid_toml(capsys, tmp_path):
    md = _article(tmp_path)
    custom = tmp_path / "article.toml"
    custom.write_text("theme = [\n", encoding="utf-8")
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--custom-path", str(custom))
    assert code == 2
    assert "error: article.toml: invalid TOML:" in err
    assert f"try:   md2xarticle diagrams {md} --custom-path {custom}" in err


def test_bad_custom_value(capsys, tmp_path):
    md = _article(tmp_path)
    custom = tmp_path / "article.toml"
    custom.write_text("size = '1x1'\n", encoding="utf-8")
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--custom-path", str(custom))
    assert code == 2
    assert "16:9" in err
    assert err.startswith("error:")
    assert f"try:   md2xarticle diagrams {md} --custom-path {custom}" in err


def test_bad_theme_name(capsys, tmp_path):
    md = _article(tmp_path)
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--theme", "neon")
    assert code == 2
    assert "error: unknown theme 'neon'" in err
    for name in BUILTIN_THEMES:
        assert name in err
    assert f"try:   md2xarticle diagrams {md} --theme {DEFAULT_THEME}" in err
    assert "invalid choice" not in err


def test_internal_error_no_traceback_unless_verbose(capsys, tmp_path, monkeypatch):
    md = _article(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(factory, "build_pipeline", boom)
    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"))
    assert code == 3
    assert "error: internal error: RuntimeError: synthetic failure" in err
    assert f"try:   md2xarticle diagrams {md} --verbose" in err
    assert "Traceback" not in err

    code, _, err = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "out"), "--verbose")
    assert code == 3
    assert "error: internal error: RuntimeError: synthetic failure" in err
    assert "Traceback" in err
    assert "RuntimeError: synthetic failure" in err
