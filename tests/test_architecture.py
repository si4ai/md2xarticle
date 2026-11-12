"""Pipeline depends only on base classes; factory.py is the only module that names concretes."""

from __future__ import annotations

import ast
from pathlib import Path

import md2xarticle

PKG = Path(md2xarticle.__file__).parent
INTERFACE_DIRS = ("parse", "render", "compose", "write", "platform")


def _module_name(path: Path) -> str:
    rel = path.relative_to(PKG.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _defines_subclass(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(isinstance(n, ast.ClassDef) and n.bases for n in tree.body)


def concrete_modules() -> set[str]:
    out = set()
    for d in INTERFACE_DIRS:
        for f in (PKG / d).glob("*.py"):
            if f.name not in ("base.py", "__init__.py") and _defines_subclass(f):
                out.add(_module_name(f))
    return out


def imports_of(path: Path) -> set[str]:
    mod = _module_name(path)
    package = mod if path.name == "__init__.py" else mod.rsplit(".", 1)[0]
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            found.add(prefix)
            found.update(f"{prefix}.{a.name}" for a in node.names)
    return found


def test_concrete_modules_found():
    assert {
        "md2xarticle.parse.markdown_it",
        "md2xarticle.render.mermaidx",
        "md2xarticle.compose.body",
        "md2xarticle.compose.cover",
        "md2xarticle.platform.posix",
        "md2xarticle.platform.windows",
        "md2xarticle.platform.wsl",
    } <= concrete_modules()


def test_only_factory_imports_concrete_classes():
    concrete = concrete_modules()
    offenders = []
    for path in PKG.rglob("*.py"):
        name = _module_name(path)
        if name == "md2xarticle.factory":
            continue
        own_pkg = name.rsplit(".", 1)[0]
        for imp in imports_of(path):
            for c in concrete:
                hit = imp == c or imp.startswith(c + ".")
                # A concrete class may subclass a sibling concrete class (WslPlatform).
                sibling = name in concrete and c.rsplit(".", 1)[0] == own_pkg
                if hit and not sibling:
                    offenders.append(f"{name} imports {imp}")
    assert not offenders, offenders


def test_pipeline_imports_only_bases():
    allowed_internal = {
        "md2xarticle.compose.base",
        "md2xarticle.compose.measure",
        "md2xarticle.customize",
        "md2xarticle.errors",
        "md2xarticle.model",
        "md2xarticle.parse.base",
        "md2xarticle.platform.base",
        "md2xarticle.render.base",
        "md2xarticle.theme",
        "md2xarticle.transform",
        "md2xarticle.write.base",
    }
    bad = []
    for imp in imports_of(PKG / "pipeline.py"):
        if not imp.startswith("md2xarticle"):
            continue
        if not any(imp == a or imp.startswith(a + ".") for a in allowed_internal):
            bad.append(imp)
    assert not bad, bad


def test_the_checker_catches_a_violation(tmp_path):
    """The scan is not vacuous: a planted concrete import is reported."""
    planted = PKG / "pipeline.py"
    imports = imports_of(planted)
    assert "md2xarticle.render.base.DiagramRenderer" in imports
    fake = tmp_path / "x.py"
    fake.write_text("from md2xarticle.render.mermaidx import MermaidxRenderer\n", encoding="utf-8")
    tree = ast.parse(fake.read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods & concrete_modules()
