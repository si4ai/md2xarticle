"""Close the empty space Mermaid's ELK layout leaves at the bottom of some
flowchart subgraphs.

With a top-down flowchart, ELK sizes a subgraph that has both an outgoing edge
and an incoming back edge as if its nodes were stacked, then lays them out in a
row, so the cluster box ends far below its last node. This module moves
everything under such a box up by the extra height. It works on Mermaid's SVG
text, edits only coordinates, and leaves any SVG it does not fully understand
unchanged.
"""

from __future__ import annotations

import re

_NUM = r"-?\d+(?:\.\d+)?(?:e-?\d+)?"
_VIEWBOX = re.compile(rf'viewBox="({_NUM}) ({_NUM}) ({_NUM}) ({_NUM})"')
_HEIGHT = re.compile(rf'(<svg\b[^>]*?\sheight=")({_NUM})(")')
_CLUSTER = re.compile(
    rf'(<g class="cluster"[^>]*><rect\b[^>]*?\sx=")({_NUM})("[^>]*?\sy=")({_NUM})("[^>]*?\swidth=")({_NUM})'
    rf'("[^>]*?\sheight=")({_NUM})(")'
)
_TRANSLATE_G = re.compile(
    rf'(<g class="(?:node\b[^"]*|edgeLabel|cluster-label)"[^>]*?transform="translate\()({_NUM})(, ?)({_NUM})(\)")'
)
_EDGE_PATH = re.compile(r'(<path d=")([^"]*)("[^>]*class="[^"]*flowchart-link[^"]*"[^>]*>)')
_DASH = re.compile(rf"(stroke-dasharray: 0 0 )({_NUM})( )")
_PAIR = re.compile(rf"({_NUM}),\s*({_NUM})|({_NUM}) ({_NUM})")
_NODE = re.compile(rf'<g class="node\b[^"]*"[^>]*?transform="translate\(({_NUM}), ?({_NUM})\)"[^>]*>(.*?)<g class="label"', re.S)
_SHAPE_Y = re.compile(rf'\s(?:y|cy)="({_NUM})"[^>]*?\s(?:height|r|ry)="({_NUM})"')
_POINTS = re.compile(r'\spoints="([^"]*)"')
_PATH_D = re.compile(r'<path[^>]*?\sd="([^"]*)"')
_ROOT_SHIFT = re.compile(r'<g class="root" transform=')

MIN_GAIN = 12.0  # px; smaller gaps are layout noise, not the ELK quirk


def _fmt(v: float) -> str:
    text = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _node_boxes(svg: str) -> list[tuple[float, float, float, float]]:
    """(cx, top, bottom, half_width) of every node, from its first shape."""
    boxes = []
    for m in _NODE.finditer(svg):
        cx, cy, body = float(m.group(1)), float(m.group(2)), m.group(3)
        ys: list[float] = []
        xs: list[float] = []
        for s in _SHAPE_Y.finditer(body):
            y, h = float(s.group(1)), float(s.group(2))
            if "cy=" in s.group(0):
                ys += [y - h, y + h]
            else:
                ys += [y, y + h]
        for p in _POINTS.finditer(body):
            nums = [float(n) for n in re.findall(_NUM, p.group(1))]
            xs += nums[0::2]
            ys += nums[1::2]
        for p in _PATH_D.finditer(body):
            for pm in _PAIR.finditer(p.group(1)):
                x = pm.group(1) or pm.group(3)
                y = pm.group(2) or pm.group(4)
                xs.append(float(x))
                ys.append(float(y))
        for s in re.finditer(rf'\sx="({_NUM})"[^>]*?\swidth="({_NUM})"', body):
            xs += [float(s.group(1)), float(s.group(1)) + float(s.group(2))]
        if not ys:
            return []  # a shape we cannot measure: do not guess
        half_w = max((abs(x) for x in xs), default=0.0)
        boxes.append((cx, cy + min(ys), cy + max(ys), half_w))
    return boxes


def _bloated_cluster(svg: str, padding: float) -> tuple[float, float] | None:
    """The first cluster (top to bottom) with extra height: (keep_y, cut_y).

    Everything at or below ``cut_y`` moves up to ``keep_y``.
    """
    nodes = _node_boxes(svg)
    if not nodes:
        return None
    clusters = [
        (float(m.group(2)), float(m.group(4)), float(m.group(6)), float(m.group(8)))
        for m in _CLUSTER.finditer(svg)
    ]
    for x, y, w, h in sorted(clusters, key=lambda c: c[1] + c[3]):
        bottom = y + h
        inside = [n for n in nodes if x <= n[0] <= x + w and y <= n[1] and n[2] <= bottom]
        inner = [c for c in clusters if c != (x, y, w, h) and x <= c[0] and c[0] + c[2] <= x + w and y <= c[1] and c[1] + c[3] <= bottom]
        content = max([n[2] for n in inside] + [c[1] + c[3] for c in inner], default=None)
        if content is None:
            continue
        keep = content + padding
        if bottom - keep < MIN_GAIN:
            continue
        # Nothing else may sit in the band that collapses.
        blocked = any(n[2] > keep and n[1] < bottom for n in nodes if n not in inside)
        blocked = blocked or any(
            keep < cy < bottom or keep < cy + ch < bottom
            for cx, cy, cw, ch in clusters
            if (cx, cy, cw, ch) != (x, y, w, h)
        )
        if not blocked:
            return keep, bottom
    return None


def _path_length(d: str) -> float:
    pts = [(float(m.group(1) or m.group(3)), float(m.group(2) or m.group(4))) for m in _PAIR.finditer(d)]
    return sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(pts, pts[1:]))


def _collapse(svg: str, keep: float, cut: float) -> str:
    gain = cut - keep

    def y_map(y: float) -> float:
        if y >= cut:
            return y - gain
        if y > keep:
            return keep
        return y

    def sub_translate(m: re.Match[str]) -> str:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}{_fmt(y_map(float(m.group(4))))}{m.group(5)}"

    def sub_cluster(m: re.Match[str]) -> str:
        y, h = float(m.group(4)), float(m.group(8))
        top, bottom = y_map(y), y_map(y + h)
        return (
            f"{m.group(1)}{m.group(2)}{m.group(3)}{_fmt(top)}{m.group(5)}{m.group(6)}"
            f"{m.group(7)}{_fmt(bottom - top)}{m.group(9)}"
        )

    def sub_path(m: re.Match[str]) -> str:
        old = m.group(2)

        def pair(p: re.Match[str]) -> str:
            if p.group(1) is not None:
                return f"{p.group(1)},{_fmt(y_map(float(p.group(2))))}"
            return f"{p.group(3)} {_fmt(y_map(float(p.group(4))))}"

        new = _PAIR.sub(pair, old)
        tail = m.group(3)
        change = _path_length(new) - _path_length(old)
        if change:
            # The dash pattern draws the line up to the arrow head; keep it in step.
            tail = _DASH.sub(lambda d: f"{d.group(1)}{_fmt(max(0.0, float(d.group(2)) + change))}{d.group(3)}", tail, count=1)
        return f"{m.group(1)}{new}{tail}"

    svg = _TRANSLATE_G.sub(sub_translate, svg)
    svg = _CLUSTER.sub(sub_cluster, svg)
    svg = _EDGE_PATH.sub(sub_path, svg)
    vb = _VIEWBOX.search(svg)
    if vb:
        h = float(vb.group(4)) - gain
        svg = svg[: vb.start()] + f'viewBox="{vb.group(1)} {vb.group(2)} {vb.group(3)} {_fmt(h)}"' + svg[vb.end():]
    svg = _HEIGHT.sub(lambda m: f"{m.group(1)}{_fmt(float(m.group(2)) - gain)}{m.group(3)}", svg, count=1)
    return svg


def close_cluster_gaps(svg: str, padding: float) -> str:
    """Return ``svg`` with the extra height under bloated subgraphs removed.

    ``padding`` is the gap kept between a subgraph's last node and its bottom
    edge (the flowchart ``padding`` setting). Unchanged when nothing applies.
    """
    if _ROOT_SHIFT.search(svg) or 'class="flowchart"' not in svg:
        return svg  # nested layouts (dagre) carry their own offsets
    for _ in range(16):
        found = _bloated_cluster(svg, padding)
        if found is None:
            break
        svg = _collapse(svg, *found)
    return svg
