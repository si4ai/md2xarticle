#!/usr/bin/env python3
"""Prove the network is cut at the OS level, then convert. Standard library only.

  python tests/offline_run.py online-control
      Control: the same probes must reach the network here, so a pass of the
      offline probe below means something.
  python tests/offline_run.py offline-convert OUT_DIR
      Run inside a network namespace with no interfaces (``unshare -rn``).
      Fails unless every probe fails first; then runs the installed
      ``md2xarticle diagrams --cover`` on the synthetic fixture and checks
      the PNGs.

Exit codes: 0 ok, 1 a check failed, 2 usage error.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dist_check import EXPECTED_PNGS, FIXTURE, png_size  # noqa: E402

TARGETS = [("1.1.1.1", 443), ("8.8.8.8", 53), ("2606:4700:4700::1111", 443)]
HOST = "pypi.org"


def probes() -> dict[str, bool]:
    """Name -> reached the network?"""
    out = {}
    for host, port in TARGETS:
        try:
            with socket.create_connection((host, port), timeout=5):
                out[f"connect {host}:{port}"] = True
        except OSError:
            out[f"connect {host}:{port}"] = False
    try:
        socket.getaddrinfo(HOST, 443)
        out[f"resolve {HOST}"] = True
    except OSError:
        out[f"resolve {HOST}"] = False
    return out


def interfaces() -> list[str]:
    """Interfaces in this process's network namespace (/sys may show the host's)."""
    return sorted(name for _, name in socket.if_nameindex())


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(line_buffering=True)
    if argv[:1] == ["online-control"] and len(argv) == 1:
        got = probes()
        for k, v in got.items():
            print(f"online-control: {k}: {'reached' if v else 'failed'}")
        if not (got["connect 1.1.1.1:443"] and got[f"resolve {HOST}"]):
            print("online-control: FAIL the probes cannot reach the network even outside the namespace", file=sys.stderr)
            return 1
        return 0
    if argv[:1] != ["offline-convert"] or len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    ifaces = interfaces()
    print(f"offline: interfaces {ifaces}")
    got = probes()
    for k, v in got.items():
        print(f"offline: {k}: {'REACHED' if v else 'failed (as required)'}")
    if any(got.values()) or [i for i in ifaces if i != "lo"]:
        print("offline: FAIL the network is reachable; refusing to call this an offline run", file=sys.stderr)
        return 1
    exe = shutil.which("md2xarticle")
    if exe is None:
        print("offline: FAIL md2xarticle is not on PATH", file=sys.stderr)
        return 1
    out = Path(argv[1])
    work = out.parent
    shutil.copyfile(FIXTURE, work / "article.md")
    p = subprocess.run([exe, "diagrams", "article.md", "-o", out.name, "--cover", "--only", "1,2,3,4"], cwd=work)
    if p.returncode != 0:
        print(f"offline: FAIL diagrams exited {p.returncode}", file=sys.stderr)
        return 1
    images = {q.name: png_size(q) for q in sorted((out / "images").iterdir())}
    if images != EXPECTED_PNGS:
        print(f"offline: FAIL images {images}, expected {EXPECTED_PNGS}", file=sys.stderr)
        return 1
    print(f"offline: converted with no network: {sorted(images)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
