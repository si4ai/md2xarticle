"""Give slanted gitGraph commit labels room.

Mermaid draws a rotated commit label down and to the left of its commit, at
fixed spacing: 50 px between commits and 90 px between branch lanes. A long
label then crosses the next lane, a connector to an earlier commit, a
neighbour's label, or the branch name tag on the left. This module measures
every label against those obstacles and widens only the gaps that need it:

- the gap between two lanes, when a label reaches the lane below or that
  lane's name tag;
- the gap between two commit columns, when a label reaches something to its left;
- a small shift of every label to the left, when a label touches a connector
  that leaves or enters its own commit.

It edits coordinates in Mermaid's SVG text only. Level labels (rotation off),
vertical graphs, and SVG it does not fully understand come back unchanged.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_NUM = r"-?\d+(?:\.\d+)?(?:e-?\d+)?"
Point = tuple[float, float]

STEP = 10.0  # px added to a gap per round
LABEL_STEP = 3.0  # px a label moves left per round
MAX_ROUNDS = 60
CLEAR = 3.0  # px kept between a label and anything else
ARROW_HALF = 4.0  # half the stroke width of a branch line
PAD = 8.0  # Mermaid's diagramPadding around the drawing

_LANE = re.compile(rf'<line x1="({_NUM})" y1="({_NUM})" x2="({_NUM})" y2="({_NUM})" class="branch branch(\d+)"/>')
_BRANCH_RECT = re.compile(
    rf'<rect class="branchLabelBkg label(\d+)"[^>]*?x="({_NUM})" y="({_NUM})" width="({_NUM})" height="({_NUM})" '
    rf'transform="translate\(({_NUM}), ({_NUM})\)"/>'
)
_BRANCH_TEXT = re.compile(rf'(<g class="label branch-label(\d+)" transform="translate\(({_NUM}), )({_NUM})(\)")')
_ARROW = re.compile(r'(<path d=")([^"]*)(" class="arrow arrow\d+"/>)')
_BULLETS = re.compile(r'<g class="commit-bullets">(.+?)</g>', re.S)
_BULLET = re.compile(r"<(circle|rect|path|line)\b([^>]*)/>")
_LABEL = re.compile(
    rf'(<g transform=")(translate\(({_NUM}), ({_NUM})\) rotate\((-?\d+), ({_NUM}), ({_NUM})\))(">)'
    rf'<rect class="commit-label-bkg" x="({_NUM})" y="({_NUM})" width="({_NUM})" height="({_NUM})"/>'
)
_TAG = re.compile(r'<polygon class="tag-label-bkg" points="([^"]*)"/>\s*<circle[^>]*class="tag-hole"/>\s*<text[^>]*class="tag-label"[^>]*>')
_VIEWBOX = re.compile(rf'viewBox="({_NUM}) ({_NUM}) ({_NUM}) ({_NUM})"')
_MAXW = re.compile(rf"max-width: ({_NUM})px")
_ATTR = re.compile(rf'\b(cx|cy|x|y|x1|y1|x2|y2|width|height|r)="({_NUM})"')


def _fmt(v: float) -> str:
    text = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _numbers(text: str) -> list[float]:
    """Numbers in an attribute, ignoring character references such as &#10;."""
    return [float(n) for n in re.findall(_NUM, re.sub(r"&#\w+;", " ", text))]


def _nearest(values: list[float], v: float) -> int:
    return min(range(len(values)), key=lambda i: (abs(values[i] - v), i))


# --- geometry ---------------------------------------------------------------


def _rotate(p: Point, deg: float, c: Point) -> Point:
    a = math.radians(deg)
    dx, dy = p[0] - c[0], p[1] - c[1]
    return (c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a))


def _seg_dist(a: Point, b: Point, c: Point, d: Point) -> float:
    def cross(o: Point, p: Point, q: Point) -> float:
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    d1, d2, d3, d4 = cross(c, d, a), cross(c, d, b), cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return 0.0

    def pt(p: Point, s: Point, e: Point) -> float:
        vx, vy = e[0] - s[0], e[1] - s[1]
        n = vx * vx + vy * vy
        t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - s[0]) * vx + (p[1] - s[1]) * vy) / n))
        return math.hypot(p[0] - s[0] - t * vx, p[1] - s[1] - t * vy)

    return min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b))


def _inside(p: Point, poly: list[Point]) -> bool:
    hit = False
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
            hit = not hit
    return hit


def _poly_seg(poly: list[Point], a: Point, b: Point) -> float:
    if _inside(a, poly) or _inside(b, poly):
        return 0.0
    return min(_seg_dist(poly[i], poly[(i + 1) % len(poly)], a, b) for i in range(len(poly)))


def _poly_poly(p: list[Point], q: list[Point]) -> float:
    if _inside(p[0], q) or _inside(q[0], p):
        return 0.0
    return min(_poly_seg(p, q[i], q[(i + 1) % len(q)]) for i in range(len(q)))


# --- the parsed graph -------------------------------------------------------


@dataclass
class _Label:
    col: int
    lane: int
    corners: list[Point]  # in Mermaid's coordinates, before any spacing
    shift: float = 0.0  # px moved left, clear of its own commit's connectors


@dataclass
class _Layout:
    lanes: list[float]  # lane y, top to bottom
    cols: list[float]  # commit x, left to right
    lane_gap: list[float] = field(default_factory=list)
    col_gap: list[float] = field(default_factory=list)

    def dx(self, col: int) -> float:
        return sum(self.col_gap[:col])

    def dy(self, lane: int) -> float:
        return sum(self.lane_gap[:lane])

    def x(self, x: float) -> float:
        return x + self.dx(_nearest(self.cols, x))

    def y(self, y: float) -> float:
        return y + self.dy(_nearest(self.lanes, y))

    def label_delta(self, label: _Label) -> Point:
        return self.dx(label.col) - label.shift, self.dy(label.lane)


def _parse_path(d: str) -> list[tuple[str, list[float]]]:
    out = []
    for cmd, args in re.findall(r"([MLA])([^MLA]*)", d):
        out.append((cmd, [float(n) for n in re.findall(_NUM, args)]))
    return out


def _arrow_segments(d: str, lay: _Layout) -> list[tuple[Point, Point]]:
    """Segments of a branch line after spacing; a corner arc becomes its two
    tangent legs, which enclose it."""
    segs: list[tuple[Point, Point]] = []
    pos: Point | None = None
    prev: Point | None = None
    for cmd, n in _parse_path(d):
        if cmd == "M":
            pos = (lay.x(n[0]), lay.y(n[1]))
            prev = None
        elif cmd == "L" and pos is not None:
            nxt = (lay.x(n[0]), lay.y(n[1]))
            segs.append((pos, nxt))
            prev, pos = pos, nxt
        elif cmd == "A" and pos is not None:
            r = n[0]
            end = (lay.x(n[-2]), lay.y(n[-1]))
            if prev is not None and prev != pos:
                ux, uy = pos[0] - prev[0], pos[1] - prev[1]
                norm = math.hypot(ux, uy)
                corner = (pos[0] + ux / norm * r, pos[1] + uy / norm * r)
                segs += [(pos, corner), (corner, end)]
            else:
                segs.append((pos, end))
            prev, pos = pos, end
    return segs


def _map_path(d: str, lay: _Layout) -> str:
    parts = []
    for cmd, n in _parse_path(d):
        if cmd == "A":
            head = ", ".join([_fmt(n[0]) + " " + _fmt(n[1])] + [_fmt(v) for v in n[2:5]])
            parts.append(f"A {head}, {_fmt(lay.x(n[5]))} {_fmt(lay.y(n[6]))}")
        else:
            parts.append(f"{cmd} {_fmt(lay.x(n[0]))} {_fmt(lay.y(n[1]))}")
    return " ".join(parts)


class _Graph:
    def __init__(self, svg: str) -> None:
        self.svg = svg
        self.lanes_raw = [
            (int(m.group(5)), float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
            for m in _LANE.finditer(svg)
        ]
        lanes = sorted({y for _, _, y, _, _ in self.lanes_raw})
        bullets = _BULLETS.search(svg)
        cols: set[float] = set()
        self.commits: list[Point] = []
        if bullets:
            for m in _BULLET.finditer(bullets.group(1)):
                a = dict(_ATTR.findall(m.group(2)))
                if m.group(1) == "circle" and float(a.get("r", 0)) >= 9:
                    centre = (float(a["cx"]), float(a["cy"]))
                elif m.group(1) == "rect" and "commit-highlight-outer" in m.group(2):
                    centre = (float(a["x"]) + float(a["width"]) / 2, float(a["y"]) + float(a["height"]) / 2)
                else:
                    continue
                cols.add(round(centre[0], 3))
                self.commits.append(centre)
        self.lay = _Layout(lanes=lanes, cols=sorted(cols))
        self.lay.lane_gap = [0.0] * max(0, len(lanes) - 1)
        self.lay.col_gap = [0.0] * max(0, len(cols) - 1)
        self.labels: list[_Label] = []
        for m in _LABEL.finditer(svg):
            tx, ty, deg, rx, ry = (float(m.group(i)) for i in (3, 4, 5, 6, 7))
            x, y, w, h = (float(m.group(i)) for i in (9, 10, 11, 12))
            box = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            corners = [(p[0] + tx, p[1] + ty) for p in (_rotate(c, deg, (rx, ry)) for c in box)]
            # The rotation centre sits 10 px left of the commit.
            self.labels.append(_Label(_nearest(self.lay.cols, rx + 10), _nearest(lanes, ry), corners))
        self.branch_rects = []
        for m in _BRANCH_RECT.finditer(svg):
            x, y, w, h, tx, ty = (float(m.group(i)) for i in range(2, 8))
            self.branch_rects.append([(x + tx, y + ty), (x + tx + w, y + ty), (x + tx + w, y + ty + h), (x + tx, y + ty + h)])
        self.tags = []
        for m in _TAG.finditer(svg):
            nums = _numbers(m.group(1))
            self.tags.append(list(zip(nums[0::2], nums[1::2])))
        self.arrows = [m.group(2) for m in _ARROW.finditer(svg)]

    def usable(self) -> bool:
        if not self.labels or not self.lay.cols or not self.lay.lanes:
            return False
        if any(y1 != y2 for _, _, y1, _, y2 in self.lanes_raw):
            return False
        # Horizontal graphs only: every lane is a horizontal line.
        return len(re.findall(r'class="branch branch\d+"', self.svg)) == len(self.lanes_raw)

    # -- collisions --

    def _label_poly(self, lab: _Label) -> list[Point]:
        dx, dy = self.lay.label_delta(lab)
        return [(x + dx, y + dy) for x, y in lab.corners]

    def collisions(self) -> list[tuple[str, int, int | None]]:
        """(kind, label index, other column or lane) for every clash."""
        lay = self.lay
        polys = [self._label_poly(lab) for lab in self.labels]
        found: list[tuple[str, int, int | None]] = []
        right = max(x2 for _, _, _, x2, _ in self.lanes_raw) if self.lanes_raw else 0.0
        right = lay.x(right)
        for i, (lab, poly) in enumerate(zip(self.labels, polys)):
            for k, ly in enumerate(lay.lanes):
                if k <= lab.lane:
                    continue
                y = lay.y(ly)
                if _poly_seg(poly, (-1e6, y), (right, y)) < CLEAR:
                    found.append(("lane", i, k))
            for d in self.arrows:
                for a, b in _arrow_segments(d, lay):
                    if _poly_seg(poly, a, b) >= ARROW_HALF + CLEAR:
                        continue
                    if abs(a[0] - b[0]) < 0.5:  # vertical: a connector at a column
                        col = _nearest([lay.x(c) for c in lay.cols], a[0])
                        found.append(("own" if col == lab.col else "col", i, col))
                    elif abs(a[1] - b[1]) < 0.5:  # horizontal: a branch line on a lane
                        lane = _nearest([lay.y(v) for v in lay.lanes], a[1])
                        if lane != lab.lane:
                            found.append(("lane", i, lane))
                    else:
                        found.append(("col", i, _nearest([lay.x(c) for c in lay.cols], min(a[0], b[0]))))
            for cx, cy in self.commits:
                p = (lay.x(cx), lay.y(cy))
                ring = [(p[0] + 10 * math.cos(t / 4 * math.pi), p[1] + 10 * math.sin(t / 4 * math.pi)) for t in range(8)]
                col = _nearest(lay.cols, cx)
                if col == lab.col and _nearest(lay.lanes, cy) == lab.lane:
                    continue
                if _poly_poly(poly, ring) < CLEAR:
                    found.append(("col" if col != lab.col else "lane", i, col if col != lab.col else _nearest(lay.lanes, cy)))
            for j, other in enumerate(polys):
                if j != i and _poly_poly(poly, other) < CLEAR and self.labels[j].col < lab.col:
                    found.append(("col", i, self.labels[j].col))
            for rect in self.branch_rects:
                lane = _nearest(lay.lanes, sum(y for _, y in rect) / 4)
                moved = [(x, lay.y(y)) for x, y in rect]
                if _poly_poly(poly, moved) < CLEAR:
                    # A label hangs below its lane, so only a lower lane's name
                    # can meet it, and that name moves down with its lane.
                    found.append(("lane", i, lane) if lane > lab.lane else ("stuck", i, None))
            for tag in self.tags:
                anchor = _nearest(lay.cols, sum(x for x, _ in tag) / len(tag))
                moved = [(x + lay.dx(anchor), lay.y(y)) for x, y in tag]
                if _poly_poly(poly, moved) < CLEAR:
                    found.append(("col", i, anchor))
        return found

    def solve(self) -> bool:
        """Widen gaps until no label clashes. False when it cannot."""
        lay = self.lay
        for _ in range(MAX_ROUNDS):
            clashes = self.collisions()
            if not clashes:
                return True
            lanes: set[int] = set()
            cols: set[int] = set()
            shift: set[int] = set()
            for kind, i, other in clashes:
                lab = self.labels[i]
                if kind == "own":
                    shift.add(i)
                elif kind == "lane" and lay.lane_gap:
                    lanes.add(min(lab.lane, len(lay.lane_gap) - 1))
                elif kind == "col" and lay.col_gap and other is not None:
                    if other == lab.col:
                        shift.add(i)
                    else:
                        cols.add(lab.col if other > lab.col else lab.col - 1)
            if not (lanes or cols or shift):
                return False
            for k in lanes:
                lay.lane_gap[k] += STEP
            for c in cols:
                if 0 <= c < len(lay.col_gap):
                    lay.col_gap[c] += STEP
            for i in shift:
                self.labels[i].shift += LABEL_STEP
        return False

    # -- output --

    def rewrite(self) -> str:
        lay = self.lay
        svg = self.svg
        extra_w = sum(lay.col_gap)
        extra_h = sum(lay.lane_gap)

        def lane_line(m: re.Match[str]) -> str:
            y = lay.y(float(m.group(2)))
            x2 = float(m.group(3)) + extra_w
            return f'<line x1="{m.group(1)}" y1="{_fmt(y)}" x2="{_fmt(x2)}" y2="{_fmt(y)}" class="branch branch{m.group(5)}"/>'

        def branch_rect(m: re.Match[str]) -> str:
            ty = float(m.group(7))
            dy = lay.dy(_nearest(lay.lanes, float(m.group(3)) + ty + float(m.group(5)) / 2))
            return m.group(0).replace(f"translate({m.group(6)}, {m.group(7)})", f"translate({m.group(6)}, {_fmt(ty + dy)})")

        def branch_text(m: re.Match[str]) -> str:
            y = float(m.group(4))
            return f"{m.group(1)}{_fmt(y + lay.dy(_nearest(lay.lanes, y + 13.5)))}{m.group(5)}"

        def shifted(attrs: str, dx: float, dy: float) -> str:
            def one(a: re.Match[str]) -> str:
                name, v = a.group(1), float(a.group(2))
                if name in ("cx", "x", "x1", "x2"):
                    v += dx
                elif name in ("cy", "y", "y1", "y2"):
                    v += dy
                return f'{name}="{_fmt(v)}"'

            attrs = _ATTR.sub(one, attrs)
            d = re.search(r'\sd="([^"]*)"', attrs)
            if d:
                nums = _numbers(d.group(1))
                pts = " ".join(f"{_fmt(x + dx)},{_fmt(y + dy)}" for x, y in zip(nums[0::2], nums[1::2]))
                cmds = re.findall(r"[ML]", d.group(1))
                pairs = pts.split(" ")
                path = "".join(f"{c} {xy} " for c, xy in zip(cmds, pairs)).strip()
                attrs = attrs[: d.start(1)] + path + attrs[d.end(1):]
            return attrs

        def bullet(m: re.Match[str]) -> str:
            a = dict(_ATTR.findall(m.group(2)))
            if "cx" in a:
                ax, ay = float(a["cx"]), float(a["cy"])
            elif m.group(1) == "rect":
                ax, ay = float(a["x"]) + float(a["width"]) / 2, float(a["y"]) + float(a["height"]) / 2
            elif m.group(1) == "line":
                ax, ay = float(a["x1"]), float(a["y1"])
            else:
                nums = _numbers(re.search(r'd="([^"]*)"', m.group(2)).group(1))
                ax, ay = nums[0] + 5, nums[1] + 5
            dx, dy = lay.dx(_nearest(lay.cols, ax)), lay.dy(_nearest(lay.lanes, ay))
            return f"<{m.group(1)}{shifted(m.group(2), dx, dy)}/>"

        labels = iter(self.labels)

        def label(m: re.Match[str]) -> str:
            lab = next(labels)
            dx, dy = lay.dx(lab.col), lay.dy(lab.lane)
            # Move the label's own coordinates (so its rotation centre stays on
            # its commit) and only the left shift in the translate.
            tx = float(m.group(3)) - lab.shift
            rx, ry = float(m.group(6)) + dx, float(m.group(7)) + dy
            head = f"{m.group(1)}translate({_fmt(tx)}, {m.group(4)}) rotate({m.group(5)}, {_fmt(rx)}, {_fmt(ry)}){m.group(8)}"
            body = m.group(0)[len(m.group(1) + m.group(2) + m.group(8)):]
            return head + re.sub(r"(<(?:rect|text)\b)([^>]*)", lambda e: e.group(1) + shifted(e.group(2), dx, dy), body)

        def tag(m: re.Match[str]) -> str:
            nums = _numbers(m.group(1))
            anchor = _nearest(lay.cols, sum(nums[0::2]) / (len(nums) // 2))
            dx, dy = lay.dx(anchor), lay.dy(_nearest(lay.lanes, max(nums[1::2]) + 15))
            pts = " ".join(f"{_fmt(x + dx)},{_fmt(y + dy)}" for x, y in zip(nums[0::2], nums[1::2]))
            out = m.group(0).replace(m.group(1), pts, 1)
            # The hole and the text follow the tag.
            return re.sub(r"(<(?:circle|text)\b)([^>]*)", lambda e: e.group(1) + shifted(e.group(2), dx, dy), out)

        svg = _LANE.sub(lane_line, svg)
        svg = _BRANCH_RECT.sub(branch_rect, svg)
        svg = _BRANCH_TEXT.sub(branch_text, svg)
        svg = _ARROW.sub(lambda m: f"{m.group(1)}{_map_path(m.group(2), lay)}{m.group(3)}", svg)
        svg = _BULLETS.sub(lambda m: '<g class="commit-bullets">' + _BULLET.sub(bullet, m.group(1)) + "</g>", svg, count=1)
        svg = re.sub(_LABEL.pattern + r'.*?</text>', label, svg)
        svg = _TAG.sub(tag, svg)

        # New bounds: everything drawn, plus Mermaid's padding.
        pts: list[Point] = []
        for lab in self.labels:
            pts += self._label_poly(lab)
        for rect in self.branch_rects:
            pts += [(x, lay.y(y)) for x, y in rect]
        for tag_poly in self.tags:
            anchor = _nearest(lay.cols, sum(x for x, _ in tag_poly) / len(tag_poly))
            pts += [(x + lay.dx(anchor), lay.y(y)) for x, y in tag_poly]
        for _, x1, y, x2, _ in self.lanes_raw:
            pts += [(x1, lay.y(y)), (x2 + extra_w, lay.y(y))]
        for d in self.arrows:
            for a, b in _arrow_segments(d, lay):
                pts += [(a[0], a[1] - ARROW_HALF), (b[0], b[1] + ARROW_HALF)]
        vb = _VIEWBOX.search(svg)
        if vb:
            x0, y0 = float(vb.group(1)), float(vb.group(2))
            x1 = max(x0 + float(vb.group(3)) + extra_w, max(p[0] for p in pts) + PAD)
            y1 = max(y0 + float(vb.group(4)) + extra_h, max(p[1] for p in pts) + PAD)
            x0 = min(x0, min(p[0] for p in pts) - PAD)
            y0 = min(y0, min(p[1] for p in pts) - PAD)
            svg = svg[: vb.start()] + f'viewBox="{_fmt(x0)} {_fmt(y0)} {_fmt(x1 - x0)} {_fmt(y1 - y0)}"' + svg[vb.end():]
            svg = _MAXW.sub(f"max-width: {_fmt(x1 - x0)}px", svg, count=1)
        return svg


def space_commit_labels(svg: str) -> str:
    """Return ``svg`` with gitGraph gaps widened so slanted labels clash with
    nothing. Unchanged when nothing clashes or the layout is not understood."""
    if 'aria-roledescription="gitGraph"' not in svg or "rotate(-45" not in svg:
        return svg
    graph = _Graph(svg)
    if not graph.usable() or not graph.collisions():
        return svg
    if not graph.solve():
        return svg
    return graph.rewrite()
