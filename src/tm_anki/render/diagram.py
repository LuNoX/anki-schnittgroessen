"""Schnittgrößenverlauf senkrecht zu den Stäben auf dem Stabskelett."""

from __future__ import annotations

import math

import numpy as np
import sympy as sp

from .. import conventions as cv
from ..fmt import math as fmt_math
from ..keypoints import KeyPoint
from ..solver import Result
from ..symbols import S, numeric_subs
from .base import Canvas, add, align_for, dot, norm, scale
from .structure import draw_fiber, draw_hinges, draw_members

SAMPLES = 64


def _lam(expr):
    expr = sp.sympify(expr)
    expr = expr.subs(numeric_subs(expr))
    f = sp.lambdify(S, expr, "numpy")
    return lambda s: np.broadcast_to(np.asarray(f(s), dtype=float), np.shape(s))


def diagram_scale(cv_: Canvas, result: Result, qty: str) -> float:
    vmax = 0.0
    for mr in result.members:
        for seg in mr.segments:
            f = _lam(seg.f(qty))
            ss = np.linspace(float(sp.N(seg.sa.subs(numeric_subs(seg.sa)))),
                             float(sp.N(seg.sb.subs(numeric_subs(seg.sb)))), SAMPLES)
            vmax = max(vmax, float(np.max(np.abs(f(ss)))))
    if vmax < 1e-12:
        return 0.0
    return cv.DIAGRAM_SCALE * cv_.geo.S / vmax


def draw_skeleton(cv_: Canvas):
    draw_members(cv_, lw=1.8)
    draw_fiber(cv_, color=cv.INK_MUTED, lw=0.8)
    draw_hinges(cv_, r_factor=0.2)


def _num(x) -> float:
    x = sp.sympify(x)
    return float(x.subs(numeric_subs(x)))


def draw_diagram(cv_: Canvas, result: Result, qty: str, kps: list[KeyPoint], visible: bool = True):
    geo, u = cv_.geo, cv_.u
    color = cv.COLORS[qty]
    side = cv.plot_sign(qty)
    k = diagram_scale(cv_, result, qty)
    vis = dict(visible=visible)

    name = f"${cv.LATEX[qty]}$"
    if geo.H < 1e-9:  # Balken: Name links neben der Stabachse
        cv_.text((geo.x0 - 1.3 * u, geo.y0), name, fs=cv.FONT_SIZE + 3, ha="right", occupy=False)

    if k == 0.0:
        cv_.text((0.5 * (geo.x0 + geo.x1), geo.y0 - 1.2 * u), f"{name[:-1]} \\equiv 0$", va="top", **vis)
    else:
        obstacles: list = []  # Stabachsen und Verlaufslinien (für die Platzierung der Werte)
        for g in geo.members:
            n = max(2, int(g.L / (0.15 * u)))
            obstacles += [g.point(s) for s in np.linspace(0, g.L, n)]
        for chain in geo.st.chains:
            obstacles += _draw_chain(cv_, result, qty, chain, k, side, color, vis)
        _place_value_labels(cv_, result, qty, kps, k, side, vis, np.array(obstacles))

    if geo.H >= 1e-9:  # Rahmen: Name oben links über dem Verlauf
        cv_.text((cv_.ext[0], cv_.ext[3] + 0.3 * u), name, fs=cv.FONT_SIZE + 3, ha="left", va="bottom",
                 occupy=False)


def _draw_chain(cv_: Canvas, result: Result, qty: str, chain, k, side, color, vis):
    geo, u = cv_.geo, cv_.u
    eps = 1e-9

    def curve_pt(g, s, v):
        return add(g.point(s), g.e3, side * v * k)

    items = []  # (g, ss, vs)
    for mi in chain.members:
        g = geo.members[mi]
        for seg in result.members[mi].segments:
            ss = np.linspace(_num(seg.sa), _num(seg.sb), SAMPLES)
            items.append((g, ss, _lam(seg.f(qty))(ss), seg))

    # Abschlusslinien: an Stabzugenden, Ecken und Sprüngen
    closers = []
    for i in range(len(items) + 1):
        left = items[i - 1] if i > 0 else None
        right = items[i] if i < len(items) else None
        corner = left and right and left[0] is not right[0] and abs(dot(left[0].e1, right[0].e1) - 1) > 1e-6
        jump = left and right and abs(left[2][-1] - right[2][0]) * k > eps
        if left and (right is None or corner or jump):
            closers.append((left[0], left[1][-1], left[2][-1]))
        if right and (left is None or corner or jump):
            closers.append((right[0], right[1][0], right[2][0]))

    for g, ss, vs, seg in items:
        if np.max(np.abs(vs)) * k < eps:
            continue
        sa, sb = ss[0], ss[-1]
        axis = [g.point(s) for s in ss]
        curve = [curve_pt(g, s, v) for s, v in zip(ss, vs)]
        cv_.polygon(axis + curve[::-1], occupy=False, fc=color, alpha=cv.FILL_ALPHA, ec="none", zorder=1, **vis)
        # Schraffur senkrecht zum Stab
        f = _lam(seg.f(qty))
        n_h = max(2, int((sb - sa) / (0.3 * u)))
        for s in np.linspace(sa, sb, n_h + 1)[1:-1]:
            v = float(f(np.array(s)))
            if abs(v) * k < 0.05 * u:
                continue
            p, c = g.point(s), curve_pt(g, s, v)
            cv_.line([p[0], c[0]], [p[1], c[1]], occupy=False, color=color, lw=0.55, alpha=0.6, zorder=1, **vis)
        xs, ys = zip(*curve)
        cv_.line(xs, ys, occupy=False, color=color, lw=1.8, zorder=3, **vis)

    # ⊕/⊖ je zusammenhängendem Vorzeichenbereich entlang gerader Stababschnitte
    markers: list = []
    run: list[tuple] = []
    for g, ss, vs, _seg in items:
        if run and abs(dot(run[-1][0].e1, g.e1) - 1) > 1e-6:
            markers += _sign_markers(cv_, run, k, side, color, vis)
            run = []
        run += [(g, s, v) for s, v in zip(ss, vs)]
    if run:
        markers += _sign_markers(cv_, run, k, side, color, vis)

    for g, s, v in closers:
        if abs(v) * k < eps:
            continue
        p, c = g.point(s), curve_pt(g, s, v)
        cv_.line([p[0], c[0]], [p[1], c[1]], occupy=False, color=color, lw=1.3, zorder=3, **vis)

    # Hindernisse für die Wertebeschriftung: Verlaufslinien und Marker (als kleiner Ring)
    obstacles = [curve_pt(g, s, v) for g, ss, vs, _ in items for s, v in zip(ss, vs)]
    ring = [(math.cos(t), math.sin(t)) for t in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
    for m in markers:
        obstacles += [m] + [add(m, d, 0.25 * u) for d in ring]
    return obstacles


def _sign_markers(cv_: Canvas, samples: list[tuple], k, side, color, vis) -> list:
    """Ein ⊕/⊖ je Vorzeichenbereich; ``samples`` = [(Stabgeometrie, s, Wert)] entlang einer Geraden.
    Gibt die Markerpositionen zurück."""
    u = cv_.u
    centers = []
    pts = [g.point(s) for g, s, _ in samples]
    vs = np.array([v for _, _, v in samples])
    xs = np.concatenate([[0.0], np.cumsum([math.dist(p, q) for p, q in zip(pts[:-1], pts[1:])])])
    sign = np.sign(np.where(np.abs(vs) * k < 1e-9, 0, vs))
    i = 0
    while i < len(vs):
        if sign[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < len(vs):
            if sign[j + 1] == sign[i]:
                j += 1
                continue
            if sign[j + 1] == 0:  # Nullstelle nur überspringen, wenn danach dasselbe Vorzeichen folgt
                nxt = j + 1
                while nxt < len(vs) and sign[nxt] == 0:
                    nxt += 1
                if nxt < len(vs) and sign[nxt] == sign[i]:
                    j = nxt
                    continue
            break
        seg = slice(i, j + 1)
        length = xs[j] - xs[i]
        if length > 0.9 * u and np.max(np.abs(vs[seg])) * k > 1.0 * u:
            # dicke Stelle, aber mit Abstand zu den Bereichsrändern und eher zur Mitte hin
            x_mid = 0.5 * (xs[i] + xs[j])
            inner = [t for t in range(i, j + 1) if xs[i] + 0.2 * length <= xs[t] <= xs[j] - 0.2 * length]
            idx = max(inner or range(i, j + 1),
                      key=lambda t: abs(vs[t]) * (1 - 0.6 * abs(xs[t] - x_mid) / length))
            if abs(vs[idx]) * k < 0.8 * u:
                i = j + 1
                continue
            g, s, v = samples[idx]
            p = add(g.point(s), g.e3, side * v * k * 0.5)
            txt = "+" if sign[i] > 0 else "−"
            cv_.ax.text(p[0], p[1], txt, fontsize=8, ha="center", va="center", color=cv.INK, zorder=5,
                        bbox=dict(boxstyle="circle,pad=0.12", fc="white", ec=color, lw=0.9), **vis)
            centers.append(p)
        i = j + 1
    return centers


def _place_value_labels(cv_: Canvas, result: Result, qty: str, kps: list[KeyPoint], k, side, vis,
                        obstacles: np.ndarray):
    geo, u = cv_.geo, cv_.u
    fs = cv.FONT_SIZE - 0.5
    placed: list[tuple[float, float, float, float]] = []
    text_pad = 0.08 * u

    def score(box) -> float:
        x0, y0, x1, y1 = box[0] - text_pad, box[1] - text_pad, box[2] + text_pad, box[3] + text_pad
        inside = 0
        if len(obstacles):
            inside = int(np.count_nonzero((obstacles[:, 0] > x0) & (obstacles[:, 0] < x1)
                                          & (obstacles[:, 1] > y0) & (obstacles[:, 1] < y1)))
        clash = sum(1 for b in placed if box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1])
        return inside + 50 * clash

    for kp in kps:
        text = fmt_math(kp.value)
        v = _num(kp.value)
        best = None
        for mi, s_expr in [(kp.member, kp.s), *kp.alts]:
            base = _label_anchor(geo, kp, mi, _num(s_expr), v, k, side, u)
            e1 = geo.members[mi].e1
            for shift in (0.0, 0.55, -0.55):  # auch leicht entlang des Stabs versetzt probieren
                cand = (add(base[0], e1, shift * u), *base[1:])
                box = cv_.text_box(cand[0], text, fs, cand[1], cand[2])
                sc = score(box) + (0.5 if shift else 0.0)
                if best is None or sc < best[0]:
                    best = (sc, cand, box)
            if best[0] == 0:
                break
        sc, (anchor, ha, va, out, c, g, s), box = best
        sc = score(box)
        for _ in range(5):  # noch Konflikt: nach außen schieben
            if sc == 0:
                break
            trial = add(anchor, out, 0.3 * u)
            tbox = cv_.text_box(trial, text, fs, ha, va)
            tsc = score(tbox)
            if tsc <= sc:
                anchor, box, sc = trial, tbox, tsc
            else:
                break
        if kp.kind == "extrem":
            p = g.point(s)
            cv_.line([p[0], c[0]], [p[1], c[1]], occupy=False, color=cv.INK_MUTED, lw=0.7,
                     linestyle=(0, (1.5, 1.5)), zorder=2, **vis)
            cv_.circle(c, 0.07 * u, occupy=False, fc=cv.INK, ec="none", zorder=4, **vis)
        placed.append(box)
        cv_.text(anchor, text, fs=fs, ha=ha, va=va, occupy=False, zorder=6, **vis)


def _label_anchor(geo, kp: KeyPoint, mi: int, s: float, v: float, k: float, side: int, u: float):
    """(Anker, ha, va, Richtung nach außen, Kurvenpunkt, Stab, s) für einen Kennwert."""
    g = geo.members[mi]
    c = add(g.point(s), g.e3, side * v * k)
    out = scale(g.e3, side * math.copysign(1.0, v))
    anchor = add(c, out, 0.2 * u)
    ha, va = align_for(out)
    if kp.kind == "ecke" and kp.member2 is not None:
        # stetiger Wert an der Ecke: diagonal neben die Ecke der beiden Ordinaten
        g2 = geo.members[kp.member2]
        P = g.point(s)
        c2 = add(P, g2.e3, side * v * k)
        diag = (c[0] + c2[0] - P[0], c[1] + c2[1] - P[1])
        sgn = side * math.copysign(1.0, v)
        out = norm(add(scale(g.e3, sgn), scale(g2.e3, sgn)))
        anchor = add(diag, out, 0.2 * u)
        ha = "left" if out[0] > 0.3 else ("right" if out[0] < -0.3 else "center")
        va = "bottom" if out[1] > 0.3 else ("top" if out[1] < -0.3 else "center")
    if kp.side in ("left", "right"):
        shift = -1.0 if kp.side == "left" else 1.0
        anchor = add(anchor, g.e1, shift * 0.3 * u)
        if abs(out[1]) >= abs(out[0]) * 0.7:  # vertikaler Versatz -> horizontal ausrichten
            ha = "right" if (g.e1[0] * shift) < 0 else "left"
        else:
            va = "top" if (g.e1[1] * shift) < 0 else "bottom"
    return anchor, ha, va, out, c, g, s
