"""The release workflow's tag-vs-version check runs in a fresh interpreter."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_YML = ROOT / ".github" / "workflows" / "release.yml"


def tag_check_script() -> str:
    text = RELEASE_YML.read_text(encoding="utf-8")
    start = text.index("python3 - <<'PY'\n") + len("python3 - <<'PY'\n")
    end = text.index("\n          PY\n", start)
    return textwrap.dedent(text[start:end])


def write_dist(folder: Path, version: str) -> None:
    dist = folder / "dist"
    dist.mkdir()
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: md2xarticle\n"
        f"Version: {version}\n"
    )
    wheel = dist / f"md2xarticle-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(f"md2xarticle-{version}.dist-info/METADATA", metadata)
    with tarfile.open(dist / f"md2xarticle-{version}.tar.gz", "w:gz"):
        pass


def run_tag_check(folder: Path, tag: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["REF_NAME"] = tag
    return subprocess.run(
        [sys.executable, "-I", "-c", tag_check_script()],
        cwd=folder,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_tag_check_accepts_matching_version(tmp_path):
    write_dist(tmp_path, "1.2.3")
    proc = run_tag_check(tmp_path, "v1.2.3")
    assert proc.returncode == 0, proc.stderr
    assert "tag v1.2.3 matches package version 1.2.3" in proc.stdout


def test_tag_check_rejects_mismatched_version(tmp_path):
    write_dist(tmp_path, "1.2.3")
    proc = run_tag_check(tmp_path, "v9.9.9")
    assert proc.returncode == 1
    assert "tag v9.9.9 does not match the built package version 1.2.3" in proc.stderr
