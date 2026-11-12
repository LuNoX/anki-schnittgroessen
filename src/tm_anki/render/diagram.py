"""Schnittgrößenverlauf senkrecht zu den Stäben auf dem Stabskelett."""

from __future__ import annotations

import math

import numpy as np
import sympy as sp

from .. import conventions as cv
from ..fmt import complex_extrema, is_simple, latex_value
from ..fmt import math as fmt_math
from ..keypoints import KeyPoint, curve_forms, extremum_offset
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
        placed_markers: list = []  # über alle Stabzüge, damit sich Marker nicht überdecken
        for chain in geo.st.chains:
            obstacles += _draw_chain(cv_, result, qty, chain, k, side, color, vis, placed_markers)
        _place_value_labels(cv_, result, qty, kps, k, side, vis, np.array(obstacles))

    if geo.H >= 1e-9:  # Rahmen: Name oben links über dem Verlauf
        cv_.text((cv_.ext[0], cv_.ext[3] + 0.3 * u), name, fs=cv.FONT_SIZE + 3, ha="left", va="bottom",
                 occupy=False)


def _draw_chain(cv_: Canvas, result: Result, qty: str, chain, k, side, color, vis, placed_markers: list):
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

    # Konturlinien an allen Teilbereichsgrenzen (bei Sprüngen und Ecken auf beiden Seiten)
    closers = []
    for i in range(len(items) + 1):
        left = items[i - 1] if i > 0 else None
        right = items[i] if i < len(items) else None
        corner = left and right and left[0] is not right[0] and abs(dot(left[0].e1, right[0].e1) - 1) > 1e-6
        jump = left and right and abs(left[2][-1] - right[2][0]) * k > eps
        if left:
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

    # ⊕/⊖ für jeden Teilbereich und darin für jeden Vorzeichenbereich einzeln
    markers: list = []
    for g, ss, vs, _seg in items:
        markers += _sign_markers(cv_, [(g, s, v) for s, v in zip(ss, vs)], k, side, color, vis, placed_markers)

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


def _sign_markers(cv_: Canvas, samples: list[tuple], k, side, color, vis, placed: list) -> list:
    """Ein ⊕/⊖ je Vorzeichenbereich; ``samples`` = [(Stabgeometrie, s, Wert)] entlang einer Geraden.
    ``placed`` = bereits gesetzte Marker (wird ergänzt). Gibt die neuen Markerpositionen zurück."""
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
        if length > 0.5 * u and np.max(np.abs(vs[seg])) * k > 0.05 * u:
            txt = "+" if sign[i] > 0 else "−"

            def draw(p):
                cv_.ax.text(p[0], p[1], txt, fontsize=8, ha="center", va="center", color=cv.INK, zorder=5,
                            bbox=dict(boxstyle="circle,pad=0.12", fc="white", ec=color, lw=0.9), **vis)
                centers.append(p)
                placed.append(p)

            def free(p):
                return all(math.dist(p, m) >= 1.0 * u for m in placed)

            # innen an einer dicken Stelle, mit Abstand zu den Bereichsrändern und eher zur Mitte hin,
            # und nicht auf einem schon gesetzten Marker (z. B. an T-Anschlüssen)
            x_mid = 0.5 * (xs[i] + xs[j])
            inner = [t for t in range(i, j + 1) if xs[i] + 0.2 * length <= xs[t] <= xs[j] - 0.2 * length]
            ranked = sorted(inner or range(i, j + 1),
                            key=lambda t: -abs(vs[t]) * (1 - 0.6 * abs(xs[t] - x_mid) / length))
            done = False
            for t in ranked:
                g, s, v = samples[t]
                if abs(v) * k < 0.8 * u:
                    break
                p = add(g.point(s), g.e3, side * v * k * 0.5)
                if free(p):
                    draw(p)
                    done = True
                    break
            if not done:  # zu schmal für innen: Marker außen neben die Kurve
                for t in ranked:
                    g, s, v = samples[t]
                    p = add(g.point(s), g.e3, side * v * k + side * math.copysign(0.45 * u, v))
                    if free(p):
                        draw(p)
                        break
        i = j + 1
    return centers


def _place_value_labels(cv_: Canvas, result: Result, qty: str, kps: list[KeyPoint], k, side, vis,
                        obstacles: np.ndarray):
    geo, u = cv_.geo, cv_.u
    fs = cv.VALUE_FONT_SIZE
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

    # Lage der Extrema als Bemaßung direkt am Stab, gemessen ab Beginn des Teilbereichs
    dim_pts = _draw_extremum_dimensions(cv_, result, kps, side, vis, placed)
    if dim_pts:
        obstacles = np.vstack([obstacles.reshape(-1, 2), np.array(dim_pts)])

    for kp in kps:
        v = _num(kp.value)
        if is_simple(kp.value):
            text = fmt_math(kp.value)
            if cv.VALUE_FULL_SIZE_FRACTIONS:
                text = text.replace("\\frac", "\\dfrac")
        else:  # unhandlicher Ausdruck (z. B. allgemeine Trapezlast): benennen, wo das Extremum liegt
            text = (f"$\\{'max' if v > 0 else 'min'}\\,{cv.LATEX[qty]}\\ "
                    f"({cv.ZERO_OF_SLOPE[qty]})$")
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

    # Kurvenform direkt an der Kurve (kurz, z. B. "quadr."), nach den Werten platziert
    fs_c = cv.CURVE_FONT_SIZE
    for crv in curve_forms(result, qty):
        text = cv.CURVE_LABELS.get(crv.degree, f"Grad {crv.degree}")
        lo, hi = _num(crv.x1_lo), _num(crv.x1_hi)
        best = None
        for frac in (0.5, 0.35, 0.65, 0.25, 0.75, 0.15, 0.85):
            x1 = lo + frac * (hi - lo)
            mi = next(m for m in crv.members
                      if _num(result.structure.members[m].s0) - 1e-9 <= x1
                      <= _num(result.structure.members[m].s0 + result.structure.members[m].length) + 1e-9)
            s = x1 - _num(result.structure.members[mi].s0)
            v = _num(result.members[mi].value(qty, sp.Float(s)))
            if abs(v) * k < 1e-9:
                continue
            g = geo.members[mi]
            out = scale(g.e3, side * math.copysign(1.0, v))
            anchor = add(add(g.point(s), g.e3, side * v * k), out, 0.22 * u)
            ha, va = align_for(out)
            box = cv_.text_box(anchor, text, fs_c, ha, va)
            sc = score(box)
            if best is None or sc < best[0]:
                best = (sc, anchor, ha, va, out, box)
            if sc == 0:
                break
        if best is None:
            continue
        sc, anchor, ha, va, out, box = best
        for _ in range(4):
            if sc == 0:
                break
            trial = add(anchor, out, 0.3 * u)
            tbox = cv_.text_box(trial, text, fs_c, ha, va)
            if score(tbox) > sc:
                break
            anchor, box, sc = trial, tbox, score(tbox)
        placed.append(box)
        cv_.text(anchor, text, fs=fs_c, ha=ha, va=va, occupy=False, zorder=6, color=cv.INK_MUTED,
                 fontstyle="italic", **vis)


def _draw_extremum_dimensions(cv_: Canvas, result: Result, kps: list[KeyPoint], side: int, vis, placed: list):
    """Bemaßung vom Beginn des Teilbereichs bis zum Extremum, auf der dem Verlauf abgewandten Seite.
    Gibt Punkte entlang der Bemaßung zurück (Hindernisse für weitere Beschriftungen)."""
    geo, u = cv_.geo, cv_.u
    fs = cv.FONT_SIZE
    pts = []
    long_names = {id(kp): name for kp, _, name in complex_extrema(result, kps) if name}
    for kp in kps:
        if kp.kind != "extrem":
            continue
        seg = next(g for g in result.members[kp.member].segments
                   if _num(g.sa) - 1e-9 <= _num(kp.s) <= _num(g.sb) + 1e-9)
        dist = extremum_offset(result, kp)
        g = geo.members[kp.member]
        n = scale(g.e3, -side * math.copysign(1.0, _num(kp.value)))  # Gegenseite des Verlaufs
        off = (0.85 if dot(n, g.e3) > 0 else 0.6) * u  # auf der Faserseite etwas weiter weg
        s0, s1 = _num(seg.sa), _num(kp.s)
        a0, a1 = g.point(s0), g.point(s1)
        p0, p1 = add(a0, n, off), add(a1, n, off)
        style = dict(occupy=False, color=cv.INK_MUTED, zorder=2, **vis)
        cv_.line([p0[0], p1[0]], [p0[1], p1[1]], lw=0.8, **style)
        tick = norm(add(g.e1, n))
        for a, p in ((a0, p0), (a1, p1)):
            e = add(p, n, 0.15 * u)
            cv_.line([a[0], e[0]], [a[1], e[1]], lw=0.6, **style)  # Hilfslinie vom Stab
            t0, t1 = add(p, tick, -0.17 * u), add(p, tick, 0.17 * u)
            cv_.line([t0[0], t1[0]], [t0[1], t1[1]], lw=0.9, **style)
        mid = add(p0, (p1[0] - p0[0], p1[1] - p0[1]), 0.5)
        anchor = add(mid, n, 0.14 * u)
        ha, va = align_for(n)
        if id(kp) in long_names:  # zu lang fürs Bild: Name im Bild, Ausdruck im Text unter dem Bild
            text = f"${long_names[id(kp)]}$"
        else:
            text = f"${latex_value(dist)}$".replace("\\frac", "\\dfrac")
        placed.append(cv_.text_box(anchor, text, fs, ha, va))
        cv_.text(anchor, text, fs=fs, ha=ha, va=va, occupy=False, zorder=6, **vis)
        pts += [add(p0, (p1[0] - p0[0], p1[1] - p0[1]), t) for t in np.linspace(0, 1, 12)]
    return pts


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
