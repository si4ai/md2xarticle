"""The dist checker's own failure paths, on synthetic archives (no build, no install)."""

from __future__ import annotations

import pytest

from tests import dist_check

GOOD_WHEEL = ["md2xarticle/__init__.py", "md2xarticle/themes/soft.json", "md2xarticle-0.1.0.dist-info/METADATA"]


def test_clean_wheel_list_passes():
    dist_check.check_file_list("wheel", GOOD_WHEEL)


@pytest.mark.parametrize("extra", ["notes/REVIEW.md", "tests/test_x.py", "secrets.txt"])
def test_stray_wheel_file_fails(extra):
    with pytest.raises(dist_check.CheckFailed, match="unexpected files|ships tests"):
        dist_check.check_file_list("wheel", [*GOOD_WHEEL, extra])


def test_stray_sdist_file_fails():
    names = ["md2xarticle-0.1.0/" + n for n in ("pyproject.toml", "src/md2xarticle/themes/soft.json", "docs/REVIEW.md")]
    with pytest.raises(dist_check.CheckFailed, match="unexpected files"):
        dist_check.check_file_list("sdist", names)


def test_hygiene_finding_in_unpacked_artifact_fails(tmp_path, monkeypatch):
    for name in dist_check.hygiene.DENYLIST_ENV:
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "unpacked" / "md2xarticle"
    root.mkdir(parents=True)
    (root / "planted.py").write_text('OUT = "/home/' + 'someone/out"\n', encoding="utf-8")
    with pytest.raises(dist_check.CheckFailed, match="1 hygiene finding"):
        dist_check.scan_hygiene("wheel", tmp_path / "unpacked")
