"""The dist checker's own failure paths, on synthetic archives (no build, no install)."""

from __future__ import annotations

import pytest

from tests import dist_check

DIST_INFO = "md2xarticle-0.1.0.dist-info/"
GOOD_WHEEL = [
    "md2xarticle/__init__.py",
    "md2xarticle/compose/body.py",
    "md2xarticle/themes/soft.json",
    "md2xarticle/py.typed",
    *(DIST_INFO + f for f in sorted(dist_check.DIST_INFO_FILES)),
]
ROOT = "md2xarticle-0.1.0/"
GOOD_SDIST = [
    ROOT + n
    for n in (
        "pyproject.toml", "README.md", "LICENSE", "PKG-INFO", ".gitignore",
        "src/md2xarticle/__init__.py", "src/md2xarticle/themes/soft.json",
        "tests/test_cli.py", "tests/snapshots/synthetic_article.md", "tests/snapshots/synthetic_article.expected.json",
    )
]


def test_clean_lists_pass():
    dist_check.check_file_list("wheel", GOOD_WHEEL)
    dist_check.check_file_list("sdist", GOOD_SDIST)


@pytest.mark.parametrize(
    "extra",
    [
        "md2xarticle/NOTES-REVIEW.md",  # a stray note inside the package
        "md2xarticle/render/debug.txt",
        "md2xarticle/themes/sample.png",
        "md2xarticle/cli.py.orig",
        "tests/test_x.py",
        "secrets.txt",
        DIST_INFO + "extra.txt",
    ],
)
def test_planted_wheel_file_fails(extra):
    with pytest.raises(dist_check.CheckFailed, match="outside the allowlist"):
        dist_check.check_file_list("wheel", [*GOOD_WHEEL, extra])


@pytest.mark.parametrize(
    "extra",
    [
        "src/md2xarticle/NOTES-REVIEW.md",
        "docs/REVIEW.md",
        "tests/REVIEW.md",  # Markdown in tests/ only as a fixture under snapshots/
        "tests/snapshots/real_article.txt",
        "ARCHITECTURE.md",
    ],
)
def test_planted_sdist_file_fails(extra):
    with pytest.raises(dist_check.CheckFailed, match="outside the allowlist"):
        dist_check.check_file_list("sdist", [*GOOD_SDIST, ROOT + extra])


def test_hygiene_finding_in_unpacked_artifact_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MD2XARTICLE_HYGIENE_DENYLIST", raising=False)
    root = tmp_path / "unpacked" / "md2xarticle"
    root.mkdir(parents=True)
    (root / "planted.py").write_text('OUT = "/home/' + 'alice/out"\n', encoding="utf-8")
    with pytest.raises(dist_check.CheckFailed, match="hygiene scan exited 1: hygiene: 1 finding"):
        dist_check.scan_hygiene("wheel", tmp_path / "unpacked")
    assert "home path in md2xarticle/planted.py" in capsys.readouterr().err


def test_clean_unpacked_artifact_passes(tmp_path, monkeypatch):
    monkeypatch.delenv("MD2XARTICLE_HYGIENE_DENYLIST", raising=False)
    root = tmp_path / "unpacked" / "md2xarticle"
    root.mkdir(parents=True)
    (root / "ok.py").write_text('OUT = "out/images"\n', encoding="utf-8")
    dist_check.scan_hygiene("wheel", tmp_path / "unpacked")
