"""Gemeinsame Bausteine fürs Zeichnen: Geometrie in Zeichenkoordinaten und eine Zeichenfläche,
die belegte Bereiche mitführt (für Platzierung von Dreibein und Beschriftungen)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

from .. import conventions as cv
from ..model import Location, Structure
from ..symbols import num

Vec = tuple[float, float]


def add(p: Vec, q: Vec, k: float = 1.0) -> Vec:
    return (p[0] + k * q[0], p[1] + k * q[1])


def scale(p: Vec, k: float) -> Vec:
    return (p[0] * k, p[1] * k)


def dot(p: Vec, q: Vec) -> float:
    return p[0] * q[0] + p[1] * q[1]


def norm(p: Vec) -> Vec:
    n = math.hypot(*p)
    return (p[0] / n, p[1] / n) if n > 1e-12 else (0.0, 0.0)


def perp(p: Vec) -> Vec:
    """Um -90° gedreht (für n = oben: t = rechts)."""
    return (p[1], -p[0])


@dataclass
class MemberGeo:
    idx: int
    p0: Vec
    p1: Vec
    e1: Vec  # Zeichenkoordinaten (y oben)
    e3: Vec
    L: float

    def point(self, s: float) -> Vec:
        return add(self.p0, self.e1, s)


class Geo:
    """Zahlenwerte der Geometrie (alle Symbole = 1), y nach oben."""

    def __init__(self, st: Structure):
        self.st = st
        self.p = {n: (num(nd.x), -num(nd.z)) for n, nd in st.nodes.items()}
        self.members = []
        for m in st.members:
            e1 = (num(m.e1[0]), -num(m.e1[1]))
            e3 = (num(m.e3[0]), -num(m.e3[1]))
            self.members.append(MemberGeo(m.idx, self.p[m.n0], self.p[m.n1], e1, e3, num(m.length)))
        xs = [p[0] for p in self.p.values()]
        ys = [p[1] for p in self.p.values()]
        self.x0, self.x1, self.y0, self.y1 = min(xs), max(xs), min(ys), max(ys)
        self.W, self.H = self.x1 - self.x0, self.y1 - self.y0
        self.S = max(self.W, self.H)
        tall = self.H > 0.5 * self.W
        self.u = self.S / (cv.U_DIVISOR_TALL if tall else cv.U_DIVISOR)

    def at(self, loc: Location) -> Vec:
        if loc.node is not None:
            return self.p[loc.node]
        return self.members[loc.member].point(num(loc.s))

    def dirs_from(self, node: str) -> list[Vec]:
        out = []
        for m in self.st.members:
            g = self.members[m.idx]
            if m.n0 == node:
                out.append(g.e1)
            elif m.n1 == node:
                out.append(scale(g.e1, -1))
        return out

    def dirs_at_point(self, p: Vec) -> list[Vec]:
        """Stabrichtungen, die von Punkt p ausgehen (Knoten oder Stabinneres)."""
        out = []
        for g in self.members:
            d0 = math.dist(p, g.p0)
            d1 = math.dist(p, g.p1)
            if d0 < 1e-9:
                out.append(g.e1)
            elif d1 < 1e-9:
                out.append(scale(g.e1, -1))
            else:
                s = dot((p[0] - g.p0[0], p[1] - g.p0[1]), g.e1)
                off = abs(dot((p[0] - g.p0[0], p[1] - g.p0[1]), perp(g.e1)))
                if 0 < s < g.L and off < 1e-9:
                    out += [g.e1, scale(g.e1, -1)]
        return out


_TEX_CMD = re.compile(r"\\(dfrac|frac|left|right|mathrm|sqrt|circ|alpha|,|\s)")


def text_size(s: str, fs: float, inch: float) -> tuple[float, float]:
    """Grobe Textgröße in Datenkoordinaten; ``inch`` = Zoll je Dateneinheit."""
    em = (fs / 72.0) / inch
    body = s.replace("$", "")
    display = "\\dfrac" in body  # Bruch in voller Größe
    tall = display or "\\frac" in body
    visible = _TEX_CMD.sub("", body)
    visible = re.sub(r"[{}^_\\]", "", visible)
    n = len(visible)
    if tall:
        n = max(1, math.ceil(n * (0.65 if display else 0.6)))
    w = (0.68 if display else 0.6) * em * max(n, 1)
    h = em * (2.6 if display else (2.0 if tall else 1.15))
    return w, h


class Canvas:
    def __init__(self, ax, geo: Geo, inch: float):
        self.ax = ax
        self.geo = geo
        self.u = geo.u
        self.inch = inch  # Zoll je Dateneinheit (für Textgrößen-Schätzung)
        self.obstacle_pts = np.zeros((0, 2))  # z. B. Verlaufsfläche im System (für Dreibein-Platzierung)
        self.boxes: list[tuple[float, float, float, float]] = []
        self.ext = [math.inf, math.inf, -math.inf, -math.inf]
        self.texts = []  # (artist, box)

    # ---- Ausdehnung und Belegung -----------------------------------------
    def grow(self, xs, ys):
        xs, ys = np.atleast_1d(xs), np.atleast_1d(ys)
        self.ext[0] = min(self.ext[0], float(xs.min()))
        self.ext[1] = min(self.ext[1], float(ys.min()))
        self.ext[2] = max(self.ext[2], float(xs.max()))
        self.ext[3] = max(self.ext[3], float(ys.max()))

    def occupy(self, xs, ys, pad: float = 0.0):
        xs, ys = np.atleast_1d(xs), np.atleast_1d(ys)
        box = (float(xs.min()) - pad, float(ys.min()) - pad, float(xs.max()) + pad, float(ys.max()) + pad)
        self.boxes.append(box)
        self.grow([box[0], box[2]], [box[1], box[3]])
        return box

    def penalty(self, points, member_clear: float | None = None) -> int:
        clear = 0.3 * self.u if member_clear is None else member_clear
        m = 0.15 * self.u  # etwas Abstand zu belegten Bereichen (sonst liest man z. B. "x1 q1" als Produkt)
        pen = 0
        for x, y in points:
            for b in self.boxes:
                if b[0] - m <= x <= b[2] + m and b[1] - m <= y <= b[3] + m:
                    pen += 1
                    break
            for g in self.geo.members:
                rel = (x - g.p0[0], y - g.p0[1])
                s = min(max(dot(rel, g.e1), 0.0), g.L)
                q = g.point(s)
                if math.dist((x, y), q) < clear:
                    pen += 2
                    break
            if len(self.obstacle_pts):
                d2 = (self.obstacle_pts[:, 0] - x) ** 2 + (self.obstacle_pts[:, 1] - y) ** 2
                if d2.min() < (0.3 * self.u) ** 2:
                    pen += 2
        return pen

    # ---- Primitive --------------------------------------------------------
    def line(self, xs, ys, occupy: bool = True, pad: float = 0.0, **kw):
        kw.setdefault("color", cv.INK)
        kw.setdefault("solid_capstyle", "butt")
        self.ax.plot(xs, ys, **kw)
        if occupy:
            self.occupy(xs, ys, pad)
        else:
            self.grow(xs, ys)

    def polygon(self, pts, occupy: bool = True, **kw):
        from matplotlib.patches import Polygon

        kw.setdefault("closed", True)
        self.ax.add_patch(Polygon(pts, **kw))
        xs, ys = zip(*pts)
        if occupy:
            self.occupy(xs, ys)
        else:
            self.grow(xs, ys)

    def circle(self, c: Vec, r: float, occupy: bool = True, **kw):
        from matplotlib.patches import Circle

        self.ax.add_patch(Circle(c, r, **kw))
        xs, ys = [c[0] - r, c[0] + r], [c[1] - r, c[1] + r]
        if occupy:
            self.occupy(xs, ys)
        else:
            self.grow(xs, ys)

    def arrow(
        self,
        tail: Vec,
        tip: Vec,
        lw: float = 1.5,
        head: float = 11,
        color=cv.INK,
        occupy: bool = True,
        zorder: float = 3,
    ):
        self.ax.annotate(
            "",
            xy=tip,
            xytext=tail,
            zorder=zorder,
            arrowprops={
                "arrowstyle": "-|>",
                "lw": lw,
                "color": color,
                "mutation_scale": head,
                "shrinkA": 0,
                "shrinkB": 0,
            },
        )
        xs, ys = [tail[0], tip[0]], [tail[1], tip[1]]
        if occupy:
            self.occupy(xs, ys, pad=0.12 * self.u)
        else:
            self.grow(xs, ys)

    def text(
        self,
        p: Vec,
        s: str,
        fs: float = cv.FONT_SIZE,
        ha: str = "center",
        va: str = "center",
        occupy: bool = True,
        color=cv.INK,
        **kw,
    ):
        w, h = text_size(s, fs, self.inch)
        x0 = {"left": p[0], "center": p[0] - w / 2, "right": p[0] - w}[ha]
        y0 = {"bottom": p[1], "center": p[1] - h / 2, "baseline": p[1] - 0.2 * h, "top": p[1] - h}[va]
        box = (x0, y0, x0 + w, y0 + h)
        art = self.ax.text(p[0], p[1], s, fontsize=fs, ha=ha, va=va, color=color, **kw)
        if occupy:
            self.boxes.append(box)
        self.grow([box[0], box[2]], [box[1], box[3]])
        self.texts.append((art, box))
        return art

    def text_box(self, p: Vec, s: str, fs: float, ha: str, va: str):
        w, h = text_size(s, fs, self.inch)
        x0 = {"left": p[0], "center": p[0] - w / 2, "right": p[0] - w}[ha]
        y0 = {"bottom": p[1], "center": p[1] - h / 2, "baseline": p[1] - 0.2 * h, "top": p[1] - h}[va]
        return (x0, y0, x0 + w, y0 + h)

    def box_free(self, box) -> bool:
        return all(not (box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1]) for b in self.boxes)


def align_for(direction: Vec) -> tuple[str, str]:
    """Textausrichtung für einen Anker, der in ``direction`` vom Bezugspunkt liegt."""
    dx, dy = direction
    if abs(dy) >= abs(dx) * 0.7:
        return "center", ("bottom" if dy > 0 else "top")
    return ("left" if dx > 0 else "right"), "center"
