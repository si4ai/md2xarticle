"""End-to-end ``md2xarticle diagrams`` on the synthetic fixture."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from md2xarticle import cli, factory
from md2xarticle.theme import load_builtin
from tests.helpers import FIXTURE_MD, SNAPSHOTS, assert_canvas

EXPECTED = SNAPSHOTS / "synthetic_article.expected.json"


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = cli.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("full") / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "md2xarticle", "diagrams", str(FIXTURE_MD), "-o", str(out_dir), "--cover", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc, out_dir


def test_exit_1_when_a_diagram_fails(full_run):
    proc, _ = full_run
    assert proc.returncode == 1, proc.stderr


def test_json_matches_snapshot(full_run):
    proc, out_dir = full_run
    data = json.loads(proc.stdout)
    assert data.pop("out_dir") == out_dir.as_posix()
    data.pop("notes")  # platform specific
    for img in data["images"]:
        if img["error"]:
            img["error"] = img["error"].splitlines()[0]
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert data == expected


def test_error_names_block_line_and_retry_command(full_run):
    proc, _ = full_run
    assert "error: diagram 05 (synthetic_article.md line 70) failed to render: Parse error" in proc.stderr
    assert f"try:   md2xarticle diagrams {FIXTURE_MD} --only 5 --verbose" in proc.stderr


def test_images_are_centered_on_exact_canvas(full_run):
    _, out_dir = full_run
    canvas = load_builtin("mono").canvas  # no --theme: the default
    names = sorted(p.name for p in (out_dir / "images").iterdir())
    assert names == ["01.png", "02.png", "03.png", "04.png", "cover.png"]
    for n in ("01", "02", "03", "04"):
        with Image.open(out_dir / "images" / f"{n}.png") as im:
            assert_canvas(im.convert("RGB"), (1600, 900), canvas, 4)
    with Image.open(out_dir / "images" / "cover.png") as im:
        assert_canvas(im.convert("RGB"), (1500, 600), canvas, 8)


def test_same_input_twice_gives_identical_pngs(full_run, tmp_path):
    """Fresh process, same platform: byte-identical PNGs."""
    _, first = full_run
    second = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "md2xarticle", "diagrams", str(FIXTURE_MD), "-o", str(second), "--cover", "--json"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    names = sorted(p.name for p in (first / "images").iterdir())
    assert names == sorted(p.name for p in (second / "images").iterdir())
    assert "cover.png" in names and len(names) == 5
    for name in names:
        assert (second / "images" / name).read_bytes() == (first / "images" / name).read_bytes(), name


def test_only_renders_selected(capsys, tmp_path):
    code, out, err = run(capsys, "diagrams", str(FIXTURE_MD), "-o", str(tmp_path), "--only", "1")
    assert code == 0, err
    assert sorted(p.name for p in (tmp_path / "images").iterdir()) == ["01.png"]
    assert "01  images/01.png  (line 14)" in out


def test_size_flag(capsys, tmp_path):
    code, _, err = run(capsys, "diagrams", str(FIXTURE_MD), "-o", str(tmp_path), "--only", "3", "--size", "1280x720", "--theme", "mono")
    assert code == 0, err
    with Image.open(tmp_path / "images" / "03.png") as im:
        assert_canvas(im.convert("RGB"), (1280, 720), load_builtin("mono").canvas, 4)


def test_custom_path_layout_override(capsys, tmp_path):
    custom = tmp_path / "article.toml"
    custom.write_text('theme = "warm"\n\n[[diagrams]]\nid = 2\nlayout = "LR"\n', encoding="utf-8")
    code, _, err = run(capsys, "diagrams", str(FIXTURE_MD), "-o", str(tmp_path / "o"), "--only", "2", "--custom-path", str(custom))
    assert code == 0, err
    from md2xarticle.compose.measure import measure
    from md2xarticle.theme import hex_to_rgb

    warm = load_builtin("warm").canvas
    with Image.open(tmp_path / "o" / "images" / "02.png") as im:
        m = measure(im.convert("RGB"), hex_to_rgb(warm))
    content_w = m.width - m.left - m.right
    content_h = m.height - m.top - m.bottom
    assert content_w > content_h  # top-down diagram now runs left to right


@pytest.mark.parametrize(
    "args",
    [
        ["--only", "9"],
        ["--size", "1000x1000"],
        ["--size", "big"],
        ["--only", "0"],
        ["--theme", "neon"],
    ],
)
def test_usage_errors_exit_2(capsys, tmp_path, args):
    with pytest.raises(SystemExit) as info:
        code = cli.main(["diagrams", str(FIXTURE_MD), "-o", str(tmp_path), *args])
        raise SystemExit(code)
    assert info.value.code == 2


def test_missing_article_and_bad_custom_file(capsys, tmp_path):
    code, _, err = run(capsys, "diagrams", str(tmp_path / "missing.md"))
    assert code == 2 and "file not found" in err
    bad = tmp_path / "bad.toml"
    bad.write_text("size = '1x1'\n", encoding="utf-8")
    code, _, err = run(capsys, "diagrams", str(FIXTURE_MD), "--custom-path", str(bad))
    assert code == 2 and "16:9" in err


def test_full_conversion_points_to_diagrams(capsys):
    code, _, err = run(capsys, "article.md")
    assert code == 2
    assert "try:   md2xarticle diagrams article.md" in err
    assert run(capsys)[0] == 2


def test_empty_article(capsys, tmp_path):
    md = tmp_path / "empty.md"
    md.write_text("", encoding="utf-8")
    code, out, _ = run(capsys, "diagrams", str(md), "-o", str(tmp_path / "o"), "--json")
    assert code == 0
    assert json.loads(out)["images"] == []


def test_internal_error_exit_3(capsys, monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(factory, "build_pipeline", boom)
    code, _, err = run(capsys, "diagrams", str(FIXTURE_MD), "-o", str(tmp_path))
    assert code == 3
    assert "internal error" in err and "--verbose" in err


def test_module_entry_point_help():
    proc = subprocess.run([sys.executable, "-m", "md2xarticle", "diagrams", "--help"], capture_output=True, text=True)
    assert proc.returncode == 0
    for flag in ("--cover", "--theme", "--custom-path", "--size", "--only", "--json"):
        assert flag in proc.stdout
