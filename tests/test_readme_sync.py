"""The README's stated Python range and pins must match pyproject.toml, and every
workflow's Python versions must sit inside that range.

The checks are plain functions over text, so the negative tests below can prove
each one fails on drifted text without touching the real files.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOWS = ROOT / ".github" / "workflows"

V = r"(3\.\d+)"
PIN_RE = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9_.-]*)==([0-9][0-9A-Za-z.]*[0-9A-Za-z])")
# "3.11 to 3.13", "3.11-3.13", "3.11–3.13", "3.11 through 3.13"
RANGE_RE = re.compile(rf"(?<![\w.]){V}\s*(?:to|through|-|–|—)\s*{V}(?!\.?\d)")
# ">=3.11", "≥ 3.11", "3.11+", "3.11 or later", "3.11 and newer", ...
FLOOR_RE = re.compile(
    rf"(?:(?:>=|≥)\s*{V}(?!\.?\d))"
    rf"|(?:(?<![\w.]){V}(?:\s*\+|\s+(?:or|and)\s+(?:later|newer|above|higher|up)\b))",
    re.IGNORECASE,
)
# Any other bare 3.x version token ("Python 3.10", "py3.14" excluded by \w).
TOKEN_RE = re.compile(rf"(?<![\w.]){V}(?!\.?\d)")


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


def supported(project: dict) -> list[str]:
    lo, hi = pyproject_range(project)
    return [f"3.{n}" for n in range(_ver(lo)[1], _ver(hi)[1] + 1)]


def pyproject_pins(project: dict) -> dict[str, str]:
    pins = {}
    for dep in project["dependencies"]:
        m = re.fullmatch(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*==\s*(\S+)\s*", dep)
        if m:
            pins[_norm(m.group(1))] = m.group(2)
    return pins


def python_problems(readme: str, project: dict) -> list[str]:
    lo, hi = pyproject_range(project)
    ok = supported(project)
    text = PIN_RE.sub(" ", readme)  # pinned package versions are not Python versions
    problems = []
    ranges = RANGE_RE.findall(text)
    if not ranges:
        problems.append("README states no Python 'X to Y' range")
    for got in ranges:
        if got != (lo, hi):
            problems.append(f"README says Python {got[0]} to {got[1]}; pyproject says {lo} to {hi}")
    text = RANGE_RE.sub(" ", text)
    for m in FLOOR_RE.finditer(text):
        floor = m.group(1) or m.group(2)
        if floor != lo:
            problems.append(f"README says Python {m.group(0).strip()!r}; pyproject's floor is {lo}")
    text = FLOOR_RE.sub(" ", text)
    for v in TOKEN_RE.findall(text):
        if v not in ok:
            problems.append(f"README mentions Python {v}, outside the supported {lo} to {hi}")
    return problems


def pin_problems(readme: str, project: dict) -> list[str]:
    problems = []
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


def readme_problems(readme: str, project: dict) -> list[str]:
    return python_problems(readme, project) + pin_problems(readme, project)


# Workflows: a line-based reader, enough for the shapes GitHub Actions matrices
# use (flow list, block list, include entries, literal python-version).
KEY = r"(python|python-version)"
FLOW_RE = re.compile(rf"^\s*-?\s*{KEY}\s*:\s*\[([^\]]*)\]")
SCALAR_RE = re.compile(rf"^\s*-?\s*{KEY}\s*:\s*['\"]?([0-9][^'\"\s#]*)['\"]?\s*(?:#.*)?$")
BLOCK_KEY_RE = re.compile(rf"^(\s*)-?\s*{KEY}\s*:\s*(?:#.*)?$")
BLOCK_ITEM_RE = re.compile(r"^(\s*)-\s*['\"]?([0-9][^'\"\s#]*)['\"]?\s*(?:#.*)?$")


def workflow_pythons(text: str) -> dict[str, set[str]]:
    """{"python": matrix values, "python-version": literal setup-python values}."""
    found: dict[str, set[str]] = {"python": set(), "python-version": set()}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if m := FLOW_RE.match(line):
            found[m.group(1)] |= {v.strip().strip("'\"") for v in m.group(2).split(",") if v.strip()}
        elif m := SCALAR_RE.match(line):
            found[m.group(1)].add(m.group(2))
        elif m := BLOCK_KEY_RE.match(line):
            j = i + 1
            while j < len(lines) and (item := BLOCK_ITEM_RE.match(lines[j])) and len(item.group(1)) >= len(m.group(1)):
                found[m.group(2)].add(item.group(2))
                j += 1
            i = j - 1
        i += 1
    return found


def workflow_problems(workflows: dict[str, str], project: dict) -> list[str]:
    """Every literal Python version in every workflow is supported, and at least
    one workflow's matrix covers the whole supported range. A workflow with no
    Python versions at all is fine."""
    ok = supported(project)
    problems = []
    full = []
    for name, text in sorted(workflows.items()):
        found = workflow_pythons(text)
        for key, vals in found.items():
            for v in sorted(vals):
                if v not in ok:
                    problems.append(f"{name}: {key} {v} is outside the supported {ok[0]} to {ok[-1]}")
        if sorted(found["python"], key=_ver) == ok:
            full.append(name)
    if not full:
        problems.append(f"no workflow's python matrix covers the supported range {ok}")
    return problems


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def _workflows() -> dict[str, str]:
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    return {p.name: p.read_text(encoding="utf-8") for p in files}


def test_readme_matches_pyproject():
    assert readme_problems(README.read_text(encoding="utf-8"), _project()) == []


def test_every_workflow_matches_supported_range():
    workflows = _workflows()
    assert "tests.yml" in workflows
    assert workflow_problems(workflows, _project()) == []


# The README checks must fail when the README drifts.

def _readme_with(extra: str) -> str:
    return README.read_text(encoding="utf-8") + "\n" + extra + "\n"


def test_drifted_python_range_is_caught():
    readme = README.read_text(encoding="utf-8").replace("Python 3.11 to 3.13", "Python 3.10 to 3.13", 1)
    assert any("Python 3.10 to 3.13" in p for p in readme_problems(readme, _project()))


def test_missing_python_range_is_caught():
    readme = RANGE_RE.sub("any version", README.read_text(encoding="utf-8"))
    assert "README states no Python 'X to Y' range" in readme_problems(readme, _project())


@pytest.mark.parametrize("text", ["Python 3.10-3.13", "Python 3.11–3.14", "3.10 through 3.13"])
def test_other_range_spellings_are_caught(text):
    assert any("pyproject says 3.11 to 3.13" in p for p in readme_problems(_readme_with(text), _project()))


@pytest.mark.parametrize(
    "text",
    ["Requires Python 3.10 or later.", "Python 3.10+ works.", "python_requires >=3.10", "Python ≥ 3.12", "3.9 and newer", "3.12 or higher"],
)
def test_wrong_free_form_floor_is_caught(text):
    assert any("pyproject's floor is 3.11" in p for p in readme_problems(_readme_with(text), _project()))


@pytest.mark.parametrize("text", ["Requires Python 3.11 or later.", "Python 3.11+", ">=3.11"])
def test_matching_free_form_floor_passes(text):
    assert readme_problems(_readme_with(text), _project()) == []


@pytest.mark.parametrize("text", ["Tested on Python 3.10.", "Python 3.14 is next."])
def test_unsupported_bare_version_is_caught(text):
    assert any("outside the supported" in p for p in readme_problems(_readme_with(text), _project()))


def test_drifted_pin_is_caught():
    readme = README.read_text(encoding="utf-8").replace("Pillow==13.0.0", "Pillow==12.0.0", 1)
    assert any(p.startswith("README pins pillow==") for p in readme_problems(readme, _project()))


def test_unstated_pin_is_caught():
    readme = README.read_text(encoding="utf-8").replace("novasvg==0.11.5", "novasvg")
    assert "pyproject pins novasvg==0.11.5; README does not state it" in readme_problems(readme, _project())


def test_pin_only_in_readme_is_caught():
    readme = _readme_with("Also pinned: requests==2.0.0")
    assert "README pins requests, which pyproject does not pin" in readme_problems(readme, _project())


# The workflow checks must fail on drift and tolerate workflows without Python.

FULL_MATRIX = 'jobs:\n  t:\n    strategy:\n      matrix:\n        python: ["3.11", "3.12", "3.13"]\n'


def test_drifted_tests_matrix_is_caught():
    workflows = _workflows()
    workflows["tests.yml"] = workflows["tests.yml"].replace('"3.11", ', "", 1)
    assert workflow_problems(workflows, _project()) != []


def test_unsupported_include_cell_in_another_workflow_is_caught():
    ci = (
        "jobs:\n  test:\n    strategy:\n      matrix:\n        include:\n"
        "          - os: ubuntu-latest\n            python: \"3.10\"\n"
        "          - os: macos-latest\n            python: '3.12'\n"
    )
    problems = workflow_problems({"tests.yml": FULL_MATRIX, "ci.yml": ci}, _project())
    assert problems == ["ci.yml: python 3.10 is outside the supported 3.11 to 3.13"]


def test_block_list_and_literal_setup_python_are_read():
    wf = (
        "jobs:\n  t:\n    strategy:\n      matrix:\n        python:\n          - \"3.11\"\n          - \"3.12\"\n          - \"3.13\"\n"
        "  r:\n    steps:\n      - uses: actions/setup-python@x\n        with:\n          python-version: \"3.9\"\n"
    )
    assert workflow_pythons(wf) == {"python": {"3.11", "3.12", "3.13"}, "python-version": {"3.9"}}
    assert workflow_problems({"a.yml": wf}, _project()) == ["a.yml: python-version 3.9 is outside the supported 3.11 to 3.13"]


def test_workflow_without_python_is_fine():
    lint = "jobs:\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"
    expr = "jobs:\n  t:\n    steps:\n      - uses: actions/setup-python@x\n        with:\n          python-version: ${{ matrix.python }}\n"
    assert workflow_problems({"tests.yml": FULL_MATRIX, "lint.yml": lint, "expr.yml": expr}, _project()) == []


def test_no_full_matrix_anywhere_is_caught():
    assert workflow_problems({"lint.yml": "jobs: {}\n"}, _project()) == [
        "no workflow's python matrix covers the supported range ['3.11', '3.12', '3.13']"
    ]
