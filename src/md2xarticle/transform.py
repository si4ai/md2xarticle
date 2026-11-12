"""Source transforms applied before rendering. Pure functions."""

from __future__ import annotations

import re

_HEADER = re.compile(r"^(\s*)(flowchart|graph)(\s+)(TD|TB|BT|RL|LR)\b", re.IGNORECASE)
_BARE_HEADER = re.compile(r"^(\s*)(flowchart|graph)\s*$", re.IGNORECASE)


def set_flowchart_direction(source: str, direction: str) -> tuple[str, bool]:
    """Rewrite the direction of a flowchart or graph header.

    Returns the new source and whether it changed. Other diagram types and
    sources with front matter or directives before the header come back as is.
    """
    lines = source.splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        m = _HEADER.match(line)
        if m:
            lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{direction}{line[m.end():]}"
            return "".join(lines), True
        m = _BARE_HEADER.match(line.rstrip("\r\n"))
        if m:
            nl = line[len(line.rstrip("\r\n")):]
            lines[i] = f"{m.group(1)}{m.group(2)} {direction}{nl}"
            return "".join(lines), True
        return source, False
    return source, False
