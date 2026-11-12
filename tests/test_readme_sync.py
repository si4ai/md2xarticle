"""The README's stated Python range and pins must match pyproject.toml, and every
workflow's Python versions must sit inside that range.

The checks are plain functions over text, so the negative tests below can prove
each one fails on drifted text without touching the real files.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOWS = ROOT / ".github" / "workflows"

V = r"(3\.\d+)"
PIN_RE = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9_.-]*)==([0-9][0-9A-Za-z.]*[0-9A-Za-z])")
# "3.11 to 3.13", "3.11-3.13", typographic dashes, "3.11 through 3.13"
RANGE_RE = re.compile(
    rf"(?<![\w.]){V}\s*(?:to|through|-|" + "\u2013|\u2014" + rf")\s*{V}(?!\.?\d)"
)
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


# Workflows: a small line-based reader (the stdlib has no YAML, and ci.yml runs
# pytest without test extras). It reads each job's matrix and every
# ``python-version`` value in that job, resolving ``${{ matrix.X }}`` to the
# matrix key X names, including ``include`` cells. ``exclude`` cells only remove
# combinations, so they add nothing.
_COMMENT = re.compile(r"\s+#.*$")
_KV = re.compile(r"^\s*(?:-\s+)?([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$")
_MATRIX_REF = re.compile(r"^\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scalar(v: str) -> str:
    v = _COMMENT.sub("", v).strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v


def _flow(v: str) -> list[str]:
    v = _COMMENT.sub("", v).strip()
    return [_scalar(x) for x in v[1:-1].split(",") if x.strip()]


def _significant(lines: list[str]) -> list[str]:
    return [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def _children(lines: list[str], i: int) -> list[str]:
    """Significant lines indented deeper than lines[i], directly after it."""
    base, out = _indent(lines[i]), []
    for ln in lines[i + 1:]:
        if _indent(ln) <= base:
            break
        out.append(ln)
    return out


def split_jobs(text: str) -> dict[str, list[str]]:
    lines = _significant(text.splitlines())
    try:
        start = next(i for i, ln in enumerate(lines) if re.match(r"^jobs\s*:\s*$", _COMMENT.sub("", ln)))
    except StopIteration:
        return {}
    jobs: dict[str, list[str]] = {}
    body = lines[start + 1:]
    if not body:
        return jobs
    level = _indent(body[0])
    name = None
    for ln in body:
        if _indent(ln) < level:
            break
        if _indent(ln) == level and (m := _KV.match(ln)):
            name = m.group(1)
            jobs[name] = []
        elif name is not None:
            jobs[name].append(ln)
    return jobs


def matrix_values(job: list[str]) -> tuple[dict[str, set[str]], bool]:
    """(key -> values, dynamic?) for the job's strategy.matrix."""
    values: dict[str, set[str]] = {}
    for i, ln in enumerate(job):
        m = _KV.match(ln)
        if not (m and m.group(1) == "matrix"):
            continue
        if _scalar(m.group(2)):
            return values, True  # e.g. matrix: ${{ fromJSON(...) }}
        block = _children(job, i)
        if not block:
            return values, False
        top = _indent(block[0])
        key = None
        for b in block:
            km = _KV.match(b)
            if _indent(b) == top and km:
                key, rest = km.group(1), km.group(2)
                if key in ("include", "exclude"):
                    continue
                if rest.startswith("["):
                    values.setdefault(key, set()).update(_flow(rest))
                elif rest:
                    values.setdefault(key, set()).add(_scalar(rest))
            elif key == "include" and km:
                values.setdefault(km.group(1), set()).add(_scalar(km.group(2)))
            elif key not in (None, "include", "exclude") and b.lstrip().startswith("- "):
                values.setdefault(key, set()).add(_scalar(b.lstrip()[2:]))
        return values, False
    return values, False


@dataclass
class JobPythons:
    literal: set[str] = field(default_factory=set)
    matrix: set[str] = field(default_factory=set)
    unresolved: list[str] = field(default_factory=list)


def job_pythons(job: list[str]) -> JobPythons:
    values, dynamic = matrix_values(job)
    out = JobPythons()
    for i, ln in enumerate(job):
        m = _KV.match(ln)
        if not (m and m.group(1) == "python-version"):
            continue
        raw = _scalar(m.group(2))
        if raw in ("|", ">", "|-", ">-"):
            out.literal.update(_scalar(c.strip()) for c in _children(job, i))
        elif ref := _MATRIX_REF.match(raw):
            key = ref.group(1)
            if dynamic:
                out.unresolved.append(f"matrix.{key} (dynamic matrix)")
            elif key not in values:
                out.unresolved.append(f"matrix.{key} (not defined in the job's matrix)")
            else:
                out.matrix.update(values[key])
        elif "${{" in raw:
            out.unresolved.append(raw)
        elif raw:
            out.literal.add(raw)
    return out


def workflow_problems(workflows: dict[str, str], project: dict) -> list[str]:
    """Per job: every Python a job uses is supported, a job whose Python comes
    from its matrix covers the whole range, and every reference resolves.
    At least one job somewhere runs the full range. Jobs without Python pass."""
    ok = supported(project)
    problems = []
    full = 0
    for wf, text in sorted(workflows.items()):
        for job, lines in split_jobs(text).items():
            got = job_pythons(lines)
            where = f"{wf} job {job}"
            for ref in got.unresolved:
                problems.append(f"{where}: cannot resolve python-version {ref}")
            for v in sorted(got.literal | got.matrix):
                if v not in ok:
                    problems.append(f"{where}: Python {v} is outside the supported {ok[0]} to {ok[-1]}")
            if got.matrix:
                missing = set(ok) - got.matrix
                if missing:
                    problems.append(f"{where}: Python matrix misses {sorted(missing, key=_ver)}")
                else:
                    full += 1
    if not full:
        problems.append(f"no job's Python matrix covers the supported range {ok}")
    return problems


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def _workflows() -> dict[str, str]:
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    return {p.name: p.read_text(encoding="utf-8") for p in files}


# Positive checks run on the real files.

def test_readme_matches_pyproject():
    assert readme_problems(README.read_text(encoding="utf-8"), _project()) == []


def test_every_workflow_matches_supported_range():
    workflows = _workflows()
    assert "tests.yml" in workflows
    assert workflow_problems(workflows, _project()) == []


def test_reader_sees_the_real_tests_matrix():
    """Guards the reader itself: if it stopped seeing tests.yml's matrix, the check above would be hollow."""
    jobs = split_jobs((WORKFLOWS / "tests.yml").read_text(encoding="utf-8"))
    assert job_pythons(jobs["pytest"]).matrix == set(supported(_project()))


# Negative checks run on synthetic text only, so another file in the repo
# (a new workflow, a README edit) can never make them pass or fail.

PROJECT = {
    "requires-python": ">=3.11",
    "classifiers": [f"Programming Language :: Python :: 3.{n}" for n in (11, 12, 13)] + ["Programming Language :: Python :: 3"],
    "dependencies": ["mermaidx==0.11.3", "Pillow==13.0.0", "markdown-it-py>=3,<5"],
}
README_OK = "Python 3.11 to 3.13.\n\nPinned to mermaidx==0.11.3 with Pillow==13.0.0.\n"


def _readme_with(extra: str) -> str:
    return README_OK + "\n" + extra + "\n"


def test_synthetic_readme_baseline_passes():
    assert readme_problems(README_OK, PROJECT) == []


def test_drifted_python_range_is_caught():
    readme = README_OK.replace("Python 3.11 to 3.13", "Python 3.10 to 3.13")
    assert "README says Python 3.10 to 3.13; pyproject says 3.11 to 3.13" in readme_problems(readme, PROJECT)


def test_missing_python_range_is_caught():
    readme = README_OK.replace("Python 3.11 to 3.13.", "Any Python.")
    assert "README states no Python 'X to Y' range" in readme_problems(readme, PROJECT)


@pytest.mark.parametrize("text", ["Python 3.10-3.13", "Python 3.11\u20133.14", "3.10 through 3.13"])
def test_other_range_spellings_are_caught(text):
    assert any("pyproject says 3.11 to 3.13" in p for p in readme_problems(_readme_with(text), PROJECT))


@pytest.mark.parametrize(
    "text",
    ["Requires Python 3.10 or later.", "Python 3.10+ works.", "python_requires >=3.10", "Python ≥ 3.12", "3.9 and newer", "3.12 or higher"],
)
def test_wrong_free_form_floor_is_caught(text):
    assert any("pyproject's floor is 3.11" in p for p in readme_problems(_readme_with(text), PROJECT))


@pytest.mark.parametrize("text", ["Requires Python 3.11 or later.", "Python 3.11+", ">=3.11"])
def test_matching_free_form_floor_passes(text):
    assert readme_problems(_readme_with(text), PROJECT) == []


@pytest.mark.parametrize("text", ["Tested on Python 3.10.", "Python 3.14 is next."])
def test_unsupported_bare_version_is_caught(text):
    assert any("outside the supported" in p for p in readme_problems(_readme_with(text), PROJECT))


def test_drifted_pin_is_caught():
    readme = README_OK.replace("Pillow==13.0.0", "Pillow==12.0.0")
    assert "README pins pillow==12.0.0; pyproject pins 13.0.0" in readme_problems(readme, PROJECT)


def test_unstated_pin_is_caught():
    readme = README_OK.replace("mermaidx==0.11.3", "mermaidx")
    assert readme_problems(readme, PROJECT) == ["pyproject pins mermaidx==0.11.3; README does not state it"]


def test_pin_only_in_readme_is_caught():
    readme = _readme_with("Also pinned: requests==2.0.0")
    assert readme_problems(readme, PROJECT) == ["README pins requests, which pyproject does not pin"]


TESTS_YML = """\
name: Tests
on: pull_request
jobs:
  pytest:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        # a comment inside the matrix
        python: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/setup-python@x
        with:
          python-version: ${{ matrix.python }}
  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@x
        with:
          python-version: "3.11"
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo no python here
"""


def _job(body: str) -> str:
    return "jobs:\n  j:\n    runs-on: ubuntu-latest\n" + textwrap.indent(textwrap.dedent(body), "    ")


def test_synthetic_workflow_baseline_passes():
    assert workflow_problems({"tests.yml": TESTS_YML}, PROJECT) == []


def test_drifted_tests_matrix_is_caught():
    drifted = TESTS_YML.replace('"3.11", ', "")
    assert workflow_problems({"tests.yml": drifted}, PROJECT) == [
        "tests.yml job pytest: Python matrix misses ['3.11']",
        "no job's Python matrix covers the supported range ['3.11', '3.12', '3.13']",
    ]


def test_drift_in_one_job_is_not_masked_by_another_full_job():
    drifted = TESTS_YML.replace('"3.11", ', "")
    problems = workflow_problems({"tests.yml": drifted, "ci.yml": TESTS_YML}, PROJECT)
    assert problems == ["tests.yml job pytest: Python matrix misses ['3.11']"]


def test_other_matrix_key_name_is_resolved():
    wf = _job("""\
        strategy:
          matrix:
            py: ["3.10", "3.11", "3.12", "3.13"]
        steps:
          - uses: actions/setup-python@x
            with:
              python-version: ${{ matrix.py }}
        """)
    assert workflow_problems({"a.yml": wf}, PROJECT) == ["a.yml job j: Python 3.10 is outside the supported 3.11 to 3.13"]


def test_include_cell_is_resolved():
    wf = _job("""\
        strategy:
          matrix:
            python: ["3.11", "3.12", "3.13"]
            include:
              - os: ubuntu-latest
                python: "3.10"
        steps:
          - uses: actions/setup-python@x
            with:
              python-version: ${{ matrix.python }}
        """)
    assert workflow_problems({"a.yml": wf}, PROJECT) == ["a.yml job j: Python 3.10 is outside the supported 3.11 to 3.13"]


def test_include_only_matrix_and_block_lists_are_read():
    wf = _job("""\
        strategy:
          matrix:
            os:
              - ubuntu-latest
            pyv:
              - "3.11"
            include:
              - pyv: '3.12'
              - os: macos-latest
                pyv: "3.13"
        steps:
          - uses: actions/setup-python@x
            with:
              python-version: ${{ matrix.pyv }}
        """)
    assert job_pythons(split_jobs(wf)["j"]).matrix == {"3.11", "3.12", "3.13"}
    assert workflow_problems({"a.yml": wf}, PROJECT) == []


def test_exclude_cell_adds_nothing():
    wf = _job("""\
        strategy:
          matrix:
            python: ["3.11", "3.12", "3.13"]
            exclude:
              - python: "3.10"
        steps:
          - uses: actions/setup-python@x
            with:
              python-version: ${{ matrix.python }}
        """)
    assert workflow_problems({"a.yml": wf}, PROJECT) == []


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ("${{ matrix.pyver }}", "matrix.pyver (not defined in the job's matrix)"),
        ("${{ env.PY }}", "${{ env.PY }}"),
    ],
)
def test_unresolvable_reference_is_caught(value, problem):
    wf = TESTS_YML.replace('python-version: "3.11"', f"python-version: {value}")
    assert workflow_problems({"tests.yml": wf}, PROJECT) == [f"tests.yml job package: cannot resolve python-version {problem}"]


def test_dynamic_matrix_is_caught():
    wf = _job("""\
        strategy:
          matrix: ${{ fromJSON(needs.setup.outputs.matrix) }}
        steps:
          - uses: actions/setup-python@x
            with:
              python-version: ${{ matrix.python }}
        """)
    assert "a.yml job j: cannot resolve python-version matrix.python (dynamic matrix)" in workflow_problems({"a.yml": wf, "tests.yml": TESTS_YML}, PROJECT)


@pytest.mark.parametrize("value", ['"3.9"', "3.10  # unquoted", "|\n  3.12\n  3.10"])
def test_unsupported_literal_is_caught(value):
    wf = TESTS_YML.replace('python-version: "3.11"', f"python-version: {value}".replace("\n", "\n          "))
    problems = workflow_problems({"tests.yml": wf}, PROJECT)
    assert len(problems) == 1 and problems[0].startswith("tests.yml job package: Python 3.") and "outside the supported" in problems[0]


def test_workflow_without_python_is_fine():
    lint = "name: Lint\non: push\njobs:\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"
    assert workflow_problems({"tests.yml": TESTS_YML, "lint.yml": lint, "empty.yml": "name: x\n"}, PROJECT) == []


def test_no_full_matrix_anywhere_is_caught():
    lint = "jobs:\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"
    assert workflow_problems({"lint.yml": lint}, PROJECT) == [
        "no job's Python matrix covers the supported range ['3.11', '3.12', '3.13']"
    ]
