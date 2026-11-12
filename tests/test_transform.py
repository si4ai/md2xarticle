from __future__ import annotations

import pytest

from md2xarticle.transform import set_flowchart_direction


@pytest.mark.parametrize(
    "src,expected",
    [
        ("flowchart TD\n  A-->B\n", "flowchart LR\n  A-->B\n"),
        ("%% caption: x\ngraph TB\n  A-->B\n", "%% caption: x\ngraph LR\n  A-->B\n"),
        ("flowchart\n  A-->B\n", "flowchart LR\n  A-->B\n"),
        ("  flowchart BT;\n", "  flowchart LR;\n"),
    ],
)
def test_rewrites_flowchart_header(src, expected):
    assert set_flowchart_direction(src, "LR") == (expected, True)


@pytest.mark.parametrize("src", ["sequenceDiagram\n  A->>B: hi\n", "", "---\ntitle: x\n---\nflowchart TD\n"])
def test_leaves_other_sources_alone(src):
    assert set_flowchart_direction(src, "LR") == (src, False)
