"""The README's stated Python range and pins must match pyproject.toml.

The checks are plain functions over text, so the negative tests below can prove
each one fails on a drifted README without touching the real files.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"

RANGE_RE = re.compile(r"\b(3\.\d+) to (3\.\d+)\b")
PIN_RE = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9_.-]*)==([0-9][0-9A-Za-z.]*[0-9A-Za-z])")
MATRIX_RE = re.compile(r"^\s*python:\s*\[([^\]]*)\]", re.MULTILINE)


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _ver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def pyproject_range(project: dict) -> tuple[str, str]:
    """(min, max): min from requires-python, max from the newest classifier."""
    m = re.fullmatch(r">=\s*(3\.\d+)", project["requires-python"].strip())
    assert m, f"requires-python is not a plain lower bound: {project['requires-python']!r}"
    tagged = [c.rsplit(" :: ", 1)[1] for c in project["classifiers"] if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", c)]
    assert tagged, "no Python 3.x classifiers"
    return m.group(1), max(tagged, key=_ver)


def pyproject_pins(project: dict) -> dict[str, str]:
    pins = {}
    for dep in project["dependencies"]:
        m = re.fullmatch(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*==\s*(\S+)\s*", dep)
        if m:
            pins[_norm(m.group(1))] = m.group(2)
    return pins


def readme_problems(readme: str, project: dict) -> list[str]:
    problems = []
    lo, hi = pyproject_range(project)
    ranges = RANGE_RE.findall(readme)
    if not ranges:
        problems.append("README states no Python 'X to Y' range")
    for got in ranges:
        if got != (lo, hi):
            problems.append(f"README says Python {got[0]} to {got[1]}; pyproject says {lo} to {hi}")
    want = pyproject_pins(project)
    seen: dict[str, set[str]] = {}
    for name, ver in PIN_RE.findall(readme):
        seen.setdefault(_norm(name), set()).add(ver)
    for name, vers in sorted(seen.items()):
        if name not in want:
            problems.append(f"README pins {name}, which pyproject does not pin")
        elif vers != {want[name]}:
            problems.append(f"README pins {name}=={'/'.join(sorted(vers))}; pyproject pins {want[name]}")
    for name in sorted(set(want) - set(seen)):
        problems.append(f"pyproject pins {name}=={want[name]}; README does not state it")
    return problems


def matrix_problems(workflow: str, project: dict) -> list[str]:
    lo, hi = pyproject_range(project)
    m = MATRIX_RE.search(workflow)
    if not m:
        return ["workflow has no python matrix"]
    got = sorted((v.strip().strip("\"'") for v in m.group(1).split(",") if v.strip()), key=_ver)
    want = [f"3.{n}" for n in range(_ver(lo)[1], _ver(hi)[1] + 1)]
    return [] if got == want else [f"CI matrix tests {got}; pyproject supports {want}"]


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def test_readme_matches_pyproject():
    assert readme_problems(README.read_text(encoding="utf-8"), _project()) == []


def test_ci_matrix_matches_supported_range():
    assert matrix_problems(WORKFLOW.read_text(encoding="utf-8"), _project()) == []


# The check must fail when the README drifts.

def test_drifted_python_range_is_caught():
    readme = README.read_text(encoding="utf-8").replace("Python 3.11 to 3.13", "Python 3.10 to 3.13", 1)
    assert any("Python 3.10 to 3.13" in p for p in readme_problems(readme, _project()))


def test_missing_python_range_is_caught():
    readme = RANGE_RE.sub("Python, any version", README.read_text(encoding="utf-8"))
    assert "README states no Python 'X to Y' range" in readme_problems(readme, _project())


def test_drifted_pin_is_caught():
    readme = README.read_text(encoding="utf-8").replace("Pillow==13.0.0", "Pillow==12.0.0", 1)
    assert any(p.startswith("README pins pillow==") for p in readme_problems(readme, _project()))


def test_unstated_pin_is_caught():
    readme = README.read_text(encoding="utf-8").replace("novasvg==0.11.5", "novasvg")
    assert "pyproject pins novasvg==0.11.5; README does not state it" in readme_problems(readme, _project())


def test_pin_only_in_readme_is_caught():
    readme = README.read_text(encoding="utf-8") + "\nAlso pinned: requests==2.0.0\n"
    assert "README pins requests, which pyproject does not pin" in readme_problems(readme, _project())


def test_drifted_ci_matrix_is_caught():
    workflow = WORKFLOW.read_text(encoding="utf-8").replace('"3.11", ', "", 1)
    assert matrix_problems(workflow, _project()) != []
