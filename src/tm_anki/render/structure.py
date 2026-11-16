"""Stäbe, gestrichelte Faser, Gelenke, Lager, x1/x3-Dreibein und Bemaßung."""

from __future__ import annotations

import itertools
import math

import numpy as np
import sympy as sp

from .. import conventions as cv
from ..fmt import latex_value
from ..model import Support
from ..symbols import num
from .base import Canvas, Geo, Vec, add, align_for, dot, norm, perp, scale

TOL = 1e-9


# --------------------------------------------------------------------------- Stäbe und Faser


def chain_polyline(geo: Geo, chain) -> list[Vec]:
    return [geo.p[n] for n in chain.nodes]


def draw_members(cv_: Canvas, lw: float = 2.6, color=cv.INK):
    geo = cv_.geo
    for chain in geo.st.chains:
        pts = chain_polyline(geo, chain)
        xs, ys = zip(*pts)
        cv_.ax.plot(xs, ys, color=color, lw=lw, solid_joinstyle="miter", solid_capstyle="butt", zorder=2)
        cv_.grow(xs, ys)


def fiber_polyline(geo: Geo, chain, offset: float) -> list[Vec]:
    """Parallel versetzter Stabzug zur Faserseite (Gehrung an Knicken)."""
    ms = [geo.members[i] for i in chain.members]
    pts = [add(ms[0].p0, ms[0].e3, offset)]
    for a_, b_ in itertools.pairwise(ms):
        if abs(dot(a_.e1, b_.e1) - 1) < 1e-9:
            pts.append(add(a_.p1, a_.e3, offset))
            continue
        # Schnitt der beiden versetzten Geraden
        p, r = add(a_.p0, a_.e3, offset), a_.e1
        q, s = add(b_.p0, b_.e3, offset), b_.e1
        den = r[0] * s[1] - r[1] * s[0]
        t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / den
        pts.append(add(p, r, t))
    pts.append(add(ms[-1].p1, ms[-1].e3, offset))
    return pts


def draw_fiber(cv_: Canvas, color=cv.INK, lw: float = 1.0):
    geo = cv_.geo
    off = 0.36 * cv_.u
    for chain in geo.st.chains:
        pts = fiber_polyline(geo, chain, off)
        xs, ys = zip(*pts)
        cv_.ax.plot(xs, ys, color=color, lw=lw, linestyle=(0, (4.5, 3)), zorder=2)
        cv_.grow(xs, ys)


def draw_hinges(cv_: Canvas, r_factor: float = 0.26):
    geo = cv_.geo
    for h in geo.st.hinges:
        cv_.circle(geo.p[h], r_factor * cv_.u, fc="white", ec=cv.INK, lw=1.4, zorder=6)


# --------------------------------------------------------------------------- Lager

_GROUND = {"unten": (0.0, 1.0), "oben": (0.0, -1.0), "links": (1.0, 0.0), "rechts": (-1.0, 0.0)}


def support_normal(geo: Geo, sup: Support) -> Vec:
    """Richtung vom Boden zum Knoten."""
    dirs = geo.dirs_from(sup.node)
    if sup.ground:
        return _GROUND[sup.ground]
    if sup.kind == "einspannung":
        v = (sum(d[0] for d in dirs), sum(d[1] for d in dirs))
        return norm(v)
    if sup.kind == "los":
        r = norm((num(sup.directions[0][0]), -num(sup.directions[0][1])))
        cands = sorted([r, scale(r, -1)], key=lambda c: (-round(c[1], 6), -round(c[0], 6)))
    else:
        cands = [(0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0)]

    def worst(c):
        return min((dot(d, c) for d in dirs), default=1.0)

    for c in cands:
        if worst(c) >= -0.75:
            return c
    return max(cands, key=worst)


#: Lager liegen unter dem Verlauf (Verlaufsfläche hat zorder 1), damit dieser im System darüber liegt
Z_SUPPORT = 0.5


def _hatch(cv_: Canvas, center: Vec, t: Vec, n: Vec, half: float, depth: float, count: int = 7, color=cv.INK):
    """Bodenlinie entlang t durch center, Schraffur auf der -n-Seite."""
    a_, b_ = add(center, t, -half), add(center, t, half)
    cv_.line([a_[0], b_[0]], [a_[1], b_[1]], lw=1.2, zorder=Z_SUPPORT, color=color)
    for k in np.linspace(-half + depth * 0.6, half, count):
        p = add(center, t, k)
        q = add(add(p, n, -depth), t, -depth * 0.8)
        cv_.line([p[0], q[0]], [p[1], q[1]], lw=0.8, zorder=Z_SUPPORT, color=color)


def draw_support(cv_: Canvas, sup: Support, color=cv.INK):
    geo, u = cv_.geo, cv_.u
    P = geo.p[sup.node]
    n = support_normal(geo, sup)
    t = perp(n)
    if sup.kind in ("fest", "los"):
        h, w = 1.05 * u, 0.62 * u
        B = add(P, n, -h)
        tri = [P, add(B, t, w), add(B, t, -w)]
        cv_.polygon(tri, fc="white", ec=color, lw=1.3, zorder=Z_SUPPORT, joinstyle="miter")
        cv_.circle(P, 0.11 * u, fc="white", ec=color, lw=1.1, zorder=Z_SUPPORT + 0.05)
        if sup.kind == "fest":
            _hatch(cv_, B, t, n, 0.95 * u, 0.32 * u, color=color)
            base = B
        else:
            gap = add(B, n, -0.22 * u)
            _hatch(cv_, gap, t, n, 0.95 * u, 0.32 * u, color=color)
            base = gap
        label_anchor = add(add(base, n, 0.3 * u), t, 1.3 * u)
    else:  # Einspannung: Wand senkrecht zu n durch P
        half = 1.05 * u
        a_, b_ = add(P, t, -half), add(P, t, half)
        cv_.line([a_[0], b_[0]], [a_[1], b_[1]], lw=2.0, zorder=Z_SUPPORT, color=color)
        for k in np.linspace(-half + 0.25 * u, half, 7):
            p = add(P, t, k)
            q = add(add(p, n, -0.42 * u), t, -0.34 * u)
            cv_.line([p[0], q[0]], [p[1], q[1]], lw=0.8, zorder=Z_SUPPORT, color=color)
        label_anchor = add(add(P, n, -0.75 * u), t, 1.3 * u)
    return label_anchor, n


def draw_supports(cv_: Canvas, labels: bool = True, color=cv.INK):
    """Lager; ``color`` gilt für die Symbole, die Bezeichnungen bleiben schwarz."""
    anchors = []
    for sup in cv_.geo.st.supports:
        anchor, n = draw_support(cv_, sup, color=color)
        anchors.append((sup, anchor, n))
    if labels:
        geo = cv_.geo
        center = (0.5 * (geo.x0 + geo.x1), 0.5 * (geo.y0 + geo.y1))
        for sup, anchor, n in anchors:
            cands = [anchor, _mirror(geo.p[sup.node], anchor, n)]
            # bevorzugt auf der Außenseite des Systems (dort liegt kein Verlauf, wenn er im System gezeichnet wird)
            cands.sort(key=lambda c: -math.dist(c, center))
            _place_label(cv_, sup.label, cands, fs=cv.FONT_SIZE)


def _mirror(P: Vec, anchor: Vec, n: Vec) -> Vec:
    """Anker auf die andere Seite (entlang t) spiegeln."""
    rel = (anchor[0] - P[0], anchor[1] - P[1])
    t = perp(n)
    k = dot(rel, t)
    return add(anchor, t, -2 * k)


def _place_label(cv_: Canvas, text: str, cands: list[Vec], fs: float, color=cv.INK):
    best, best_pen = cands[0], math.inf
    for c in cands:
        box = cv_.text_box(c, f"${text}$", fs, "center", "center")
        pts = [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3]), c]
        pen = cv_.penalty(pts, member_clear=0.2 * cv_.u)
        if pen < best_pen:
            best, best_pen = c, pen
    cv_.text(best, f"${text}$", fs=fs, color=color)


# --------------------------------------------------------------------------- Dreibein


def draw_triads(cv_: Canvas, color=cv.INK):
    geo, u = cv_.geo, cv_.u
    L_ax = 1.35 * u
    for chain in geo.st.chains:
        g = geo.members[chain.members[0]]
        P0 = g.p0
        sup = geo.st.support_at(chain.nodes[0])
        back = 2.3 * u + (0.6 * u if sup is not None and sup.kind == "einspannung" else 0.0)
        cands = [
            add(P0, g.e1, -back),
            add(add(P0, g.e1, 1.0 * u), g.e3, 1.25 * u),
            add(add(P0, g.e1, -back), g.e3, -1.7 * u),
            add(add(P0, g.e1, min(0.3 * g.L, 4 * u)), g.e3, 1.25 * u),
            add(add(P0, g.e1, 1.0 * u), g.e3, -2.8 * u),
            add(add(P0, g.e1, min(0.5 * g.L, 6 * u)), g.e3, 1.25 * u),
        ]
        best, best_pen = cands[0], math.inf
        for O in cands:
            pts = []
            for k in np.linspace(0, 1, 6):
                pts.append(add(O, g.e1, k * L_ax))
                pts.append(add(O, g.e3, k * L_ax))
            for d, name in ((g.e1, "x_1"), (g.e3, "x_3")):  # Beschriftungen mit prüfen
                anchor = add(add(O, d, L_ax), d, 0.22 * u)
                ha, va = align_for(d)
                b = cv_.text_box(anchor, f"${name}$", cv.FONT_SIZE - 1, ha, va)
                pts += [(b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3])]
            pen = cv_.penalty(pts, member_clear=0.6 * u)  # Abstand auch zur Faser halten
            if pen < best_pen - 1e-9:
                best, best_pen = O, pen
        O = best
        t1, t3 = add(O, g.e1, L_ax), add(O, g.e3, L_ax)
        cv_.arrow(O, t1, lw=1.1, head=8, color=color)
        cv_.arrow(O, t3, lw=1.1, head=8, color=color)
        for tip, d, name in ((t1, g.e1, "x_1"), (t3, g.e3, "x_3")):
            anchor = add(tip, d, 0.22 * u)
            ha, va = align_for(d)
            cv_.text(anchor, f"${name}$", fs=cv.FONT_SIZE - 1, ha=ha, va=va, color=color)


# --------------------------------------------------------------------------- Bemaßung


def _load_positions(geo: Geo) -> list[tuple[sp.Expr, sp.Expr]]:
    """Exakte (X, Y)-Positionen von Knoten und Lastpunkten (Y nach oben)."""
    st = geo.st
    pts = [(n.x, -n.z) for n in st.nodes.values()]

    def member_xy(mi, s):
        m = st.members[mi]
        x, z = m.point(s)
        return (sp.simplify(x), sp.simplify(-z))

    for pf in st.point_forces:
        if pf.at.member is not None:
            pts.append(member_xy(pf.at.member, pf.at.s))
    for pm in st.point_moments:
        if pm.at.member is not None:
            pts.append(member_xy(pm.at.member, pm.at.s))
    for ll in st.line_loads:
        pts.append(member_xy(ll.member, ll.sa))
        pts.append(member_xy(ll.member, ll.sb))
    return pts


def _unique_sorted(vals: list[sp.Expr]) -> list[sp.Expr]:
    out: list[sp.Expr] = []
    for v in sorted(vals, key=num):
        if not out or num(v) - num(out[-1]) > TOL:
            out.append(v)
    return out


def draw_dimensions(cv_: Canvas):
    geo, u = cv_.geo, cv_.u
    pts = _load_positions(geo)
    fs = cv.FONT_SIZE - 1
    tick = 0.22 * u
    if geo.W > TOL:
        xs = _unique_sorted([p[0] for p in pts])
        y = cv_.ext[1] - 0.8 * u
        x_num = [num(x) for x in xs]
        cv_.line([x_num[0], x_num[-1]], [y, y], occupy=False, lw=0.7, color=cv.INK_MUTED)
        for x in x_num:
            cv_.line([x - tick * 0.7, x + tick * 0.7], [y - tick, y + tick], occupy=False, lw=0.9, color=cv.INK_MUTED)
        for xa, xb in itertools.pairwise(xs):
            cv_.text(
                ((num(xa) + num(xb)) / 2, y - 0.15 * u), f"${latex_value(xb - xa)}$", fs=fs, va="top", occupy=False
            )
    if geo.H > TOL:
        ys = _unique_sorted([p[1] for p in pts])
        x = cv_.ext[0] - 1.0 * u
        y_num = [num(v) for v in ys]
        cv_.line([x, x], [y_num[0], y_num[-1]], occupy=False, lw=0.7, color=cv.INK_MUTED)
        for v in y_num:
            cv_.line([x - tick, x + tick], [v - tick * 0.7, v + tick * 0.7], occupy=False, lw=0.9, color=cv.INK_MUTED)
        for ya, yb in itertools.pairwise(ys):
            cv_.text(
                (x - 0.15 * u, (num(ya) + num(yb)) / 2), f"${latex_value(yb - ya)}$", fs=fs, ha="right", occupy=False
            )
