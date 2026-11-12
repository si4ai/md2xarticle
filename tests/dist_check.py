#!/usr/bin/env python3
"""Check built distributions end to end. Standard library only.

For the wheel and the sdist in DIST_DIR:
1. Every file matches an allowlist by location and type: package code is
   ``.py``, built-in themes ``.json``, plus an optional ``py.typed`` marker.
   A stray ``.md`` (or any other type) under the package fails.
2. The hygiene scan is clean over the unpacked contents.
3. It installs into a fresh venv; ``md2xarticle --help`` exits 0, and a
   ``diagrams --cover`` run on the synthetic fixture writes the expected PNGs
   at the exact canvas sizes, from the installed copy (not the source tree).

Usage: python tests/dist_check.py DIST_DIR
Exit codes: 0 all good, 1 a check failed, 2 usage error.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
# The one hygiene scanner. dist_check runs from a repo checkout; tools/ does not ship.
SCANNER = HERE.parent / "tools" / "hygiene.py"

FIXTURE = HERE / "snapshots" / "synthetic_article.md"
BINARY_ONLY = "mermaidx,novasvg,quickjs-ng,Pillow"
EXPECTED_PNGS = {"01.png": (1600, 900), "02.png": (1600, 900), "03.png": (1600, 900), "04.png": (1600, 900), "cover.png": (1500, 600)}
# Package code is Python; the only data files are the built-in theme JSON.
PACKAGE_SUFFIXES = {".py", ".json"}
PACKAGE_NAMES = {"py.typed"}
# Wheel metadata that hatchling writes (LICENSE via license-files).
DIST_INFO_FILES = {"METADATA", "WHEEL", "RECORD", "entry_points.txt", "licenses/LICENSE"}
# sdist: fixed top-level files, the package, and the test suite.
SDIST_FILES = {"README.md", "LICENSE", "pyproject.toml", "PKG-INFO", ".gitignore"}
TEST_SUFFIXES = {".py", ".json"}
# Synthetic Markdown fixtures live only in tests/snapshots/.
FIXTURE_DIR, FIXTURE_SUFFIXES = "tests/snapshots/", {".md", ".json"}


class CheckFailed(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise CheckFailed(msg)


def wheel_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        return z.namelist()


def sdist_names(path: Path) -> list[str]:
    with tarfile.open(path) as t:
        return [m.name for m in t.getmembers() if m.isfile()]


def _package_file(rel: str) -> bool:
    """``rel`` is relative to the ``md2xarticle/`` package directory."""
    name = PurePosixPath(rel).name
    return name in PACKAGE_NAMES or PurePosixPath(rel).suffix in PACKAGE_SUFFIXES


def allowed(kind: str, name: str) -> bool:
    if kind == "wheel":
        top, _, rest = name.partition("/")
        if top == "md2xarticle":
            return _package_file(rest)
        if top.startswith("md2xarticle-") and top.endswith(".dist-info"):
            return rest in DIST_INFO_FILES
        return False
    _, _, rel = name.partition("/")  # drop the md2xarticle-<version>/ root
    if rel in SDIST_FILES:
        return True
    if rel.startswith("src/md2xarticle/"):
        return _package_file(rel[len("src/md2xarticle/"):])
    if rel.startswith(FIXTURE_DIR):
        return PurePosixPath(rel).suffix in FIXTURE_SUFFIXES
    if rel.startswith("tests/"):
        return PurePosixPath(rel).suffix in TEST_SUFFIXES
    return False


# Every built-in theme must ship; tests/test_dist_check.py keeps this in step with the package.
THEMES = ("mono", "soft", "warm", "x-light", "x-dark")


def check_file_list(kind: str, names: list[str]) -> None:
    check(bool(names), f"{kind}: empty archive")
    bad = [n for n in names if not allowed(kind, n)]
    check(not bad, f"{kind}: files outside the allowlist: {bad[:10]}")
    joined = "\n".join(names)
    missing = [t for t in THEMES if f"md2xarticle/themes/{t}.json" not in joined]
    check(not missing, f"{kind}: built-in themes missing: {missing}")


def unpack(kind: str, path: Path, dest: Path) -> None:
    if kind == "wheel":
        with zipfile.ZipFile(path) as z:
            z.extractall(dest)
    else:
        with tarfile.open(path) as t:
            t.extractall(dest, filter="data")


def scan_hygiene(kind: str, root: Path) -> None:
    """tools/hygiene.py over the unpacked artifact; it never prints matched text."""
    check(SCANNER.is_file(), f"hygiene scanner missing: {SCANNER.name}")
    p = subprocess.run([sys.executable, str(SCANNER), "--root", str(root)], capture_output=True, text=True, encoding="utf-8")
    for line in p.stdout.splitlines():
        if line.startswith("- "):
            print(f"hygiene ({kind}): {line[2:]}", file=sys.stderr)
    check(p.returncode == 0, f"{kind}: hygiene scan exited {p.returncode}: {p.stdout.splitlines()[0] if p.stdout else p.stderr.strip()}")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    check(data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name}: not a PNG")
    return struct.unpack(">II", data[16:24])


def run(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def install_and_convert(kind: str, artifact: Path, work: Path) -> None:
    env_dir = work / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
    bindir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    py = bindir / ("python.exe" if os.name == "nt" else "python")
    exe = bindir / ("md2xarticle.exe" if os.name == "nt" else "md2xarticle")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}

    p = run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", "--only-binary", BINARY_ONLY, str(artifact)], work, env)
    check(p.returncode == 0, f"{kind}: pip install failed:\n{p.stdout}\n{p.stderr}")

    p = run([str(py), "-c", "import md2xarticle; print(md2xarticle.__file__)"], work, env)
    check(p.returncode == 0, f"{kind}: import failed: {p.stderr}")
    check(Path(p.stdout.strip()).resolve().is_relative_to(env_dir.resolve()), f"{kind}: md2xarticle imported from outside the fresh venv")

    p = run([str(exe), "--help"], work, env)
    check(p.returncode == 0, f"{kind}: md2xarticle --help exited {p.returncode}: {p.stderr}")
    check("diagrams" in p.stdout, f"{kind}: --help does not mention diagrams")

    article = work / "article.md"
    shutil.copyfile(FIXTURE, article)
    p = run([str(exe), "diagrams", "article.md", "-o", "out", "--cover", "--only", "1,2,3,4"], work, env)
    check(p.returncode == 0, f"{kind}: diagrams exited {p.returncode}:\n{p.stdout}\n{p.stderr}")
    images = work / "out" / "images"
    got = {q.name: png_size(q) for q in sorted(images.iterdir())}
    check(got == EXPECTED_PNGS, f"{kind}: images {got}, expected {EXPECTED_PNGS}")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.split("\n\n")[-2], file=sys.stderr)
        return 2
    dist = Path(argv[0])
    wheels = sorted(dist.glob("md2xarticle-*.whl"))
    sdists = sorted(dist.glob("md2xarticle-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        print(f"dist_check: expected one wheel and one sdist in {dist}", file=sys.stderr)
        return 2
    failed = 0
    for kind, artifact, names in (("wheel", wheels[0], wheel_names(wheels[0])), ("sdist", sdists[0], sdist_names(sdists[0]))):
        with tempfile.TemporaryDirectory(prefix="md2x-dist-") as tmp:
            work = Path(tmp)
            try:
                check_file_list(kind, names)
                unpack(kind, artifact, work / "unpacked")
                scan_hygiene(kind, work / "unpacked")
                install_and_convert(kind, artifact.resolve(), work)
                print(f"dist_check: {kind} ok ({artifact.name}, {len(names)} files)")
            except CheckFailed as exc:
                failed += 1
                print(f"dist_check: FAIL {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
