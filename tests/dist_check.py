#!/usr/bin/env python3
"""Check built distributions end to end. Standard library only.

For the wheel and the sdist in DIST_DIR:
1. The file list holds only package files (nothing stray, no private notes).
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
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hygiene  # noqa: E402

FIXTURE = HERE / "snapshots" / "synthetic_article.md"
BINARY_ONLY = "mermaidx,novasvg,quickjs-ng,Pillow"
EXPECTED_PNGS = {"01.png": (1600, 900), "02.png": (1600, 900), "03.png": (1600, 900), "04.png": (1600, 900), "cover.png": (1500, 600)}
SDIST_TOP = {"src", "tests", "README.md", "LICENSE", "pyproject.toml", "PKG-INFO", ".gitignore"}


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


def check_file_list(kind: str, names: list[str]) -> None:
    check(bool(names), f"{kind}: empty archive")
    if kind == "wheel":
        bad = [n for n in names if not (n.startswith("md2xarticle/") or n.split("/", 1)[0].endswith(".dist-info"))]
        check(not any(n.startswith("tests/") for n in names), "wheel: ships tests/")
    else:
        bad = [n for n in names if len(n.split("/")) < 2 or n.split("/")[1] not in SDIST_TOP]
    check(not bad, f"{kind}: unexpected files: {bad[:10]}")
    check("md2xarticle/themes/soft.json" in "\n".join(names), f"{kind}: built-in themes missing")


def unpack(kind: str, path: Path, dest: Path) -> None:
    if kind == "wheel":
        with zipfile.ZipFile(path) as z:
            z.extractall(dest)
    else:
        with tarfile.open(path) as t:
            t.extractall(dest, filter="data")


def scan_hygiene(kind: str, root: Path) -> None:
    deny = hygiene.load_denylist(hygiene.denylist_from_env())
    findings = hygiene.scan(root, deny)
    for f in findings:
        print(f"hygiene ({kind}): {f}", file=sys.stderr)
    check(not findings, f"{kind}: {len(findings)} hygiene finding(s); matched text is not printed")


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
