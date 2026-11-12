"""The skip budget fails a run with one skip too many, and only then."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.skip_budget import EXPECTED_SKIPS

ROOT = Path(__file__).resolve().parent.parent


def run_with_skips(tmp_path: Path, n: int) -> subprocess.CompletedProcess[str]:
    body = "import pytest\n\ndef test_ok():\n    pass\n" + "".join(
        f"\n\ndef test_skip_{i}():\n    pytest.skip('synthetic')\n" for i in range(n)
    )
    (tmp_path / "test_synthetic.py").write_text(body, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "tests.skip_budget", "-p", "no:cacheprovider",
         "-c", str(tmp_path / "pytest.ini"), str(tmp_path)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )


def test_within_budget_passes(tmp_path):
    proc = run_with_skips(tmp_path, EXPECTED_SKIPS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "skip budget exceeded" not in proc.stdout


def test_one_over_budget_fails_visibly(tmp_path):
    proc = run_with_skips(tmp_path, EXPECTED_SKIPS + 1)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert f"skip budget exceeded: {EXPECTED_SKIPS + 1} skipped, expected at most {EXPECTED_SKIPS}" in proc.stdout
