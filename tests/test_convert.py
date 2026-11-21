"""The full conversion: ``md2xarticle ARTICLE.md`` writes article.html,
outline.txt, images and manifest.json in one run."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from md2xarticle import cli, factory
from md2xarticle.errors import DiagramRenderError
from md2xarticle.model import Article
from md2xarticle.pipeline import ConvertOptions, DiagramsOptions, Pipeline
from md2xarticle.render.base import DiagramRenderer
from md2xarticle.theme import load_builtin
from md2xarticle.write.base import ArticleWriter
from tests.helpers import FIXTURE_MD, SNAPSHOTS, assert_canvas, fake_rendered

EMAIL = "pat.sample" + "@" + "corp-mail.biz"
PLAIN = "# Plain Title\n\nIntro text.\n\n## First\n\nBody.\n\n## Second\n\nMore body.\n"
DEEP = "# T\n\n## A\n\n### B\n\n#### C\n\nText.\n"
ONE_DIAGRAM = (
    "# One\n\n## Flow\n\nThe steps are:\n\n"
    "```mermaid\nflowchart LR\n  A[Read] --> B[Write]\n```\n\nDone.\n"
)


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = cli.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def write_md(tmp_path: Path, text: str, name: str = "article.md") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


# --- end to end on the synthetic fixture (one broken diagram) ----------------


@pytest.fixture(scope="module")
def fixture_run(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("convert") / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "md2xarticle", str(FIXTURE_MD), "-o", str(out_dir), "--cover", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc, out_dir


def test_one_run_writes_every_output(fixture_run):
    _, out_dir = fixture_run
    names = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*") if p.is_file())
    assert names == [
        "article.html",
        "images/01.png",
        "images/02.png",
        "images/03.png",
        "images/04.png",
        "images/cover.png",
        "manifest.json",
        "outline.txt",
    ]


def test_failed_diagram_exits_1_with_retry_hint(fixture_run):
    proc, _ = fixture_run
    assert proc.returncode == 1, proc.stderr
    assert "error: diagram 05 (synthetic_article.md line 70) failed to render" in proc.stderr
    assert "--only 5 --verbose" in proc.stderr


def test_json_summary_follows_the_output_contract(fixture_run):
    proc, out_dir = fixture_run
    data = json.loads(proc.stdout)
    assert data["ok"] is False
    assert data["out_dir"] == out_dir.as_posix()
    assert data["html"] == (out_dir / "article.html").as_posix()
    assert data["outline"] == (out_dir / "outline.txt").as_posix()
    assert data["manifest"] == (out_dir / "manifest.json").as_posix()
    assert data["images"] == 4
    assert data["cover"] is True
    assert data["warnings"] == []
    assert data["privacy_findings"] == []
    assert [(f["order"], f["source_line"]) for f in data["failed"]] == [(5, 70)]
    assert data["failed"][0]["error"].startswith("Parse error")
    assert isinstance(data["notes"], list)


def test_manifest_matches_the_diagrams_snapshot(fixture_run):
    _, out_dir = fixture_run
    data = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    expected = json.loads((SNAPSHOTS / "synthetic_article.manifest.json").read_text(encoding="utf-8"))
    assert data == expected


def test_html_markers_match_the_manifest(fixture_run):
    _, out_dir = fixture_run
    html = (out_dir / "article.html").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    for image in manifest["images"]:
        assert f"<p>{image['marker']}</p>" in html
    # The failed diagram was not written, so it keeps the plain numbered marker.
    assert "<p>[Image 05]</p>" in html
    assert "<title>Pipeline Sketch</title>" in html
    assert "<h1" not in html and "flowchart" not in html and "sequenceDiagram" not in html


def test_outline_file_matches_the_outline_command(fixture_run, capsys):
    _, out_dir = fixture_run
    code, out, _ = run(capsys, "outline", str(FIXTURE_MD))
    assert code == 0
    assert (out_dir / "outline.txt").read_text(encoding="utf-8") == out


def test_images_are_centered_on_exact_canvas(fixture_run):
    _, out_dir = fixture_run
    canvas = load_builtin("mono").canvas
    with Image.open(out_dir / "images" / "01.png") as im:
        assert_canvas(im.convert("RGB"), (1600, 900), canvas, 4)
    with Image.open(out_dir / "images" / "cover.png") as im:
        assert im.size == (1500, 600)


# --- acceptance rows -----------------------------------------------------------


def test_plain_markdown_has_no_images_and_exits_0(capsys, tmp_path):
    md = write_md(tmp_path, PLAIN)
    out = tmp_path / "out"
    code, stdout, err = run(capsys, str(md), "-o", str(out), "--json")
    assert code == 0, err
    data = json.loads(stdout)
    assert data["ok"] is True and data["images"] == 0 and data["cover"] is False
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {"version": 1, "source": "article.md", "cover": None, "images": []}
    html = (out / "article.html").read_text(encoding="utf-8")
    assert "<h2>First</h2>" in html and "<h2>Second</h2>" in html
    assert (out / "outline.txt").read_text(encoding="utf-8") == "Outline (X levels)\n  H   First\n  H   Second\n"
    assert not (out / "images").exists()


def test_deep_headings_never_reach_the_html_beyond_subheading(capsys, tmp_path):
    md = write_md(tmp_path, DEEP)
    out = tmp_path / "out"
    code, _, err = run(capsys, str(md), "-o", str(out))
    assert code == 0, err
    html = (out / "article.html").read_text(encoding="utf-8")
    assert "<h2>A</h2>" in html and "<h3>B</h3>" in html and "<p><strong>C</strong></p>" in html
    assert "<h4" not in html
    assert "[bold lead-in] C" in (out / "outline.txt").read_text(encoding="utf-8")


def test_empty_file_is_an_empty_article(capsys, tmp_path):
    md = write_md(tmp_path, "")
    out = tmp_path / "out"
    code, stdout, _ = run(capsys, str(md), "-o", str(out), "--json")
    assert code == 0
    assert json.loads(stdout)["images"] == 0
    assert (out / "article.html").exists() and (out / "outline.txt").exists()


def test_same_input_twice_gives_identical_bytes(capsys, tmp_path):
    md = write_md(tmp_path, ONE_DIAGRAM)
    for name in ("a", "b"):
        code, _, err = run(capsys, str(md), "-o", str(tmp_path / name))
        assert code == 0, err
    for rel in ("article.html", "outline.txt", "manifest.json", "images/01.png"):
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes(), rel


def test_text_summary_names_outline_images_and_next_step(capsys, tmp_path):
    md = write_md(tmp_path, ONE_DIAGRAM)
    out = tmp_path / "out"
    code, stdout, err = run(capsys, str(md), "-o", str(out))
    assert code == 0, err
    assert f"article.md -> {out.as_posix()}/" in stdout
    assert "Outline (X levels)\n  H   Flow\n" in stdout
    assert '01  images/01.png  Flow  (after "The steps are:")' in stdout
    assert f"Wrote {out.as_posix()}/article.html, {out.as_posix()}/outline.txt, {out.as_posix()}/manifest.json, 1 image in " in stdout
    assert "Next: open" in stdout and "[Image NN]" in stdout


def test_privacy_findings_exit_1_and_files_are_still_written(capsys, tmp_path):
    md = write_md(tmp_path, f"# T\n\nWrite to {EMAIL} for details.\n")
    out = tmp_path / "out"
    code, stdout, _ = run(capsys, str(md), "-o", str(out), "--check-privacy", "--json")
    assert code == 1
    data = json.loads(stdout)
    assert data["ok"] is False
    assert data["privacy_findings"] == [{"file": md.as_posix(), "line": 3, "kind": "email"}]
    assert (out / "article.html").exists() and (out / "manifest.json").exists()
    assert EMAIL not in stdout


def test_without_the_flag_there_is_no_privacy_scan(capsys, tmp_path):
    md = write_md(tmp_path, f"# T\n\nWrite to {EMAIL}.\n")
    code, stdout, _ = run(capsys, str(md), "-o", str(tmp_path / "out"), "--json")
    assert code == 0
    assert json.loads(stdout)["privacy_findings"] == []


def test_heading_fallback_exits_1_with_the_next_command(capsys, tmp_path):
    md = write_md(tmp_path, "# Title\n\n## A\n\n# Stray\n\nText.\n")
    code, _, err = run(capsys, str(md), "-o", str(tmp_path / "out"))
    assert code == 1
    assert "warning: heading on line 5 ('Stray') has no row in the shifted mapping; treated as Heading" in err
    assert f"try:   md2xarticle {md} --heading-map flat" in err
    code, _, err = run(capsys, str(md), "-o", str(tmp_path / "flat"), "--heading-map", "flat")
    assert code == 0, err


def test_only_writes_selected_images_and_full_html(capsys, tmp_path):
    out = tmp_path / "out"
    code, stdout, err = run(capsys, str(FIXTURE_MD), "-o", str(out), "--only", "2", "--json")
    assert code == 0, err
    assert sorted(p.name for p in (out / "images").iterdir()) == ["02.png"]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert [i["order"] for i in manifest["images"]] == [2]
    html = (out / "article.html").read_text(encoding="utf-8")
    assert "<p>[Image 01]</p>" in html and "<p>[Image 02: Decisions]</p>" in html


def test_default_output_folder_comes_from_platform(capsys, tmp_path, monkeypatch):
    md = write_md(tmp_path, PLAIN)
    monkeypatch.chdir(tmp_path)
    code, _, err = run(capsys, "article.md")
    assert code == 0, err
    assert (tmp_path / "out" / "article.html").exists()
    assert md.exists()


def test_open_flag_opens_the_output_folder(capsys, tmp_path, monkeypatch):
    opened = []
    platform_cls = type(factory.detect_platform())

    class Recording(platform_cls):  # type: ignore[misc, valid-type]
        def open_result(self, path):
            opened.append(path)

    monkeypatch.setattr(factory, "detect_platform", Recording)
    md = write_md(tmp_path, PLAIN)
    out = tmp_path / "out"
    code, _, err = run(capsys, str(md), "-o", str(out), "--open")
    assert code == 0, err
    assert opened == [out]


# --- usage and internal errors ------------------------------------------------


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (["--size", "1000x1000"], "16:9"),
        (["--theme", "neon"], "unknown theme"),
        (["--only", "9"], "--only 9"),
        (["--heading-map", "mystery"], "invalid choice"),
        (["--renderer", "nope"], "unknown renderer"),
    ],
)
def test_usage_errors_exit_2(capsys, tmp_path, args, needle):
    with pytest.raises(SystemExit) as info:
        code = cli.main([str(FIXTURE_MD), "-o", str(tmp_path / "out"), *args])
        raise SystemExit(code)
    _, err = capsys.readouterr()
    assert info.value.code == 2
    assert needle in err
    assert "try:   md2xarticle " in err
    assert "md2xarticle diagrams" not in err


def test_missing_article_exits_2_and_names_the_convert_command(capsys, tmp_path):
    missing = tmp_path / "missing.md"
    code, _, err = run(capsys, str(missing))
    assert code == 2
    assert "file not found" in err
    assert f"try:   md2xarticle {missing}" in err


def test_no_arguments_prints_help_and_exits_2(capsys):
    code, _, err = run(capsys)
    assert code == 2 and "md2xarticle ARTICLE.md" in err


def test_internal_error_exit_3(capsys, monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(factory, "build_pipeline", boom)
    md = write_md(tmp_path, PLAIN)
    code, _, err = run(capsys, str(md), "-o", str(tmp_path / "out"))
    assert code == 3
    assert "internal error" in err and f"try:   md2xarticle {md} --verbose" in err
    assert "Traceback" not in err


def test_convert_help_lists_the_readme_flags():
    proc = subprocess.run(
        [sys.executable, "-m", "md2xarticle", "article.md", "--help"], capture_output=True, text=True
    )
    assert proc.returncode == 0
    for flag in (
        "--out", "--cover", "--theme", "--custom-path", "--size", "--only", "--renderer",
        "--heading-map", "--check-privacy", "--json", "--verbose", "--open",
    ):
        assert flag in proc.stdout


# --- Pipeline.run against the base classes only --------------------------------


class FakeRenderer(DiagramRenderer):
    name = "fake"

    def available(self) -> bool:
        return True

    def render(self, source, theme):
        if "broken" in source:
            raise DiagramRenderError("synthetic failure")
        return fake_rendered(400, 200, theme.canvas)


class RecordingWriter(ArticleWriter):
    name = "recording"

    def __init__(self) -> None:
        self.articles: list[Article] = []

    def write(self, article, out_dir):
        self.articles.append(article)
        path = Path(out_dir) / "recorded.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
        return [path]


def make_pipeline(writers):
    theme = load_builtin("mono")
    return Pipeline(
        parser=factory.PARSERS["markdown-it"](),
        renderer=FakeRenderer(),
        body=factory.BODY_COMPOSERS["body"](theme),
        make_cover=lambda t, s=None: factory.COVER_COMPOSERS["cover"](theme, title=t, subtitle=s),
        platform=factory.detect_platform(),
        theme=theme,
        writers=writers,
    )


TWO = (
    "# Doc\n\n## Good\n\nBefore good:\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\n"
    "## Bad\n\n```mermaid\nflowchart LR\n  broken\n```\n"
)


def test_pipeline_hands_every_writer_one_shaped_article(tmp_path):
    writer = RecordingWriter()
    md = TWO
    result = make_pipeline([writer]).run(
        md, ConvertOptions(diagrams=DiagramsOptions(out_dir=tmp_path), source="doc.md")
    )
    assert result.written == [tmp_path / "recorded.txt"]
    (article,) = writer.articles
    assert article.source == "doc.md"
    assert article.markdown == md
    assert article.document is result.diagrams.document
    assert [(i.order, i.file, i.marker) for i in article.images] == [(1, "images/01.png", "[Image 01: Good]")]
    assert [r.index for r in result.diagrams.failed] == [2]
    assert result.findings is None


def test_pipeline_scans_privacy_only_when_asked(tmp_path):
    text = f"# T\n\n{EMAIL}\n"
    opts = DiagramsOptions(out_dir=tmp_path)
    scanned = make_pipeline([]).run(text, ConvertOptions(diagrams=opts, deny=()))
    assert [(f.line, f.kind) for f in scanned.findings] == [(3, "email")]
    assert make_pipeline([]).run(text, ConvertOptions(diagrams=opts)).findings is None


def test_pipeline_reports_heading_fallbacks(tmp_path):
    result = make_pipeline([]).run(
        "# T\n\n# Stray\n", ConvertOptions(diagrams=DiagramsOptions(out_dir=tmp_path))
    )
    assert [e.text for e in result.outline.fallbacks] == ["Stray"]
