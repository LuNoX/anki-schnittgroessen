"""Lasten zeichnen: Streckenlasten, Einzelkräfte (mit Winkel), Einzelmomente."""

from __future__ import annotations

import math

import numpy as np

from .. import conventions as cv
from ..symbols import num
from .base import Canvas, Vec, add, align_for, dot, norm, scale
from .structure import _place_label


def _load_dir(d) -> Vec:
    return norm((num(d[0]), -num(d[1])))


def draw_line_loads(cv_: Canvas, color=cv.INK):
    geo, u = cv_.geo, cv_.u
    st = geo.st
    if not st.line_loads:
        return
    qmax = max(max(abs(num(ll.qa)), abs(num(ll.qb))) for ll in st.line_loads) or 1.0
    Hq, gap = 2.0 * u, 0.1 * u

    # gleiche Beschriftung am selben Punkt (z. B. Spitze zweier Dreieckslasten) nur einmal, mittig
    from collections import Counter

    shared_labels: Counter = Counter()
    for ll in st.line_loads:
        g_ = geo.members[ll.member]
        for text, s_loc in ll.labels:
            p = g_.point(num(s_loc))
            shared_labels[(text, round(p[0], 6), round(p[1], 6))] += 1
    drawn_labels: set = set()

    # Gruppenenden bestimmen (keine Abschlusslinie an inneren Stoßstellen einer Gruppe)
    def ends(ll):
        g = geo.members[ll.member]
        return g.point(num(ll.sa)), g.point(num(ll.sb))

    for ll in st.line_loads:
        g = geo.members[ll.member]
        d = _load_dir(ll.d)
        sa, sb = num(ll.sa), num(ll.sb)
        qa, qb = num(ll.qa), num(ll.qb)

        def qn(s, sa=sa, sb=sb, qa=qa, qb=qb):
            return qa + (qb - qa) * (s - sa) / (sb - sa)

        def h(s):
            return Hq * qn(s) / qmax

        if ll.bezug == "projektion":
            ref = max(dot(g.point(sa), scale(d, -1)), dot(g.point(sb), scale(d, -1)))

            def tail(s):
                p = g.point(s)
                extra = ref - dot(p, scale(d, -1))
                return add(p, d, -(h(s) + extra + gap))
        else:

            def tail(s):
                return add(g.point(s), d, -(h(s) + math.copysign(gap, qn(s) or 1)))

        along = (sb - sa) * (num(ll.factor) if ll.bezug == "projektion" else 1.0)
        n = max(3, round(along / (0.6 * u)) + 1)
        for s in np.linspace(sa, sb, n):
            if abs(h(s)) < 0.22 * u:
                continue
            tip = add(g.point(s), d, -math.copysign(gap, qn(s)))
            cv_.arrow(tail(s), tip, lw=0.9, head=7, color=color)
        t_a, t_b = tail(sa), tail(sb)
        cv_.line([t_a[0], t_b[0]], [t_a[1], t_b[1]], lw=1.1, color=color, zorder=3)
        p_a, p_b = ends(ll)
        others = [o for o in st.line_loads if o is not ll and o.group == ll.group]
        start_inner = any(math.dist(ends(o)[1], p_a) < 1e-9 for o in others)
        end_inner = any(math.dist(ends(o)[0], p_b) < 1e-9 for o in others)
        if not start_inner and abs(h(sa)) > 1e-9:
            base = add(p_a, d, -math.copysign(gap, qa or 1))
            cv_.line([t_a[0], base[0]], [t_a[1], base[1]], lw=1.1, color=color, zorder=3)
        if not end_inner and abs(h(sb)) > 1e-9:
            base = add(p_b, d, -math.copysign(gap, qb or 1))
            cv_.line([t_b[0], base[0]], [t_b[1], base[1]], lw=1.1, color=color, zorder=3)
        for text, s_loc in ll.labels:
            s0 = num(s_loc)
            span = sb - sa
            key = (text, round(g.point(s0)[0], 6), round(g.point(s0)[1], 6))
            if key in drawn_labels:  # z. B. Spitze zweier Dreieckslasten: gleiche Beschriftung nur einmal
                continue
            drawn_labels.add(key)
            shared = shared_labels[key] > 1
            if abs(qa - qb) > 1e-12 and not shared:  # am Lastende etwas nach innen (Platz für Dreibein)
                inset = min(0.45 * u, 0.15 * span)
                if abs(s0 - sa) < 1e-9:
                    s0 += inset
                elif abs(s0 - sb) < 1e-9:
                    s0 -= inset
            cands = [s0]
            if abs(qa - qb) < 1e-12:  # konstante Last: Beschriftung darf entlang der Last ausweichen
                cands += [min(max(s0 + f * span, sa + 0.08 * span), sb - 0.08 * span) for f in (-0.2, 0.2, -0.35, 0.35)]
            for s in cands:
                out = scale(d, -math.copysign(1, qn(s) or 1))
                anchor = add(tail(s), out, 0.25 * u)
                ha, va = align_for(out)
                if cv_.box_free(cv_.text_box(anchor, f"${text}$", cv.FONT_SIZE, ha, va)):
                    break
            else:  # nichts frei: an der ursprünglichen Stelle
                out = scale(d, -math.copysign(1, qn(s0) or 1))
                anchor = add(tail(s0), out, 0.25 * u)
                ha, va = align_for(out)
            cv_.text(anchor, f"${text}$", ha=ha, va=va, color=color)


def draw_point_forces(cv_: Canvas, color=cv.INK):
    geo, u = cv_.geo, cv_.u
    st = geo.st
    Lf = 2.4 * u
    for pf in st.point_forces:
        P = geo.at(pf.at)
        ang = math.radians(pf.angle_deg)
        d = (math.cos(ang), math.sin(ang))
        if num(pf.magnitude) < 0:
            d = scale(d, -1)
        gap = 0.32 * u if (pf.at.node is not None and pf.at.node in st.hinges) else 0.1 * u
        dirs = geo.dirs_at_point(P)
        along = any(dot(m, scale(d, -1)) > 0.9 for m in dirs)
        through = along and any(dot(m, d) > 0.9 for m in dirs)  # Stab auch vor dem Punkt: Kraft im Stabinneren
        if through:
            # axiale Kraft im Stabinneren: parallel zum Stab, leicht zur faserabgewandten Seite versetzt,
            # Spitze an der Angriffsstelle (sonst läge der Pfeil auf der Stabachse)
            g_ax = next(g for g in geo.members if abs(abs(dot(g.e1, d)) - 1) < 1e-6)
            n_off = scale(g_ax.e3, -1)
            tip = add(add(P, d, -gap), n_off, 0.5 * u)
            tail = add(tip, d, -Lf)
            anchor = add(tail, d, -0.25 * u)
            out = scale(d, -1)
        elif along:  # Pfeil würde auf dem Stab liegen: vom Punkt weg zeichnen (Zug)
            tail = add(P, d, gap)
            tip = add(tail, d, Lf)
            anchor = add(tip, d, 0.25 * u)
            out = d
        else:
            tip = add(P, d, -gap)
            tail = add(tip, d, -Lf)
            anchor = add(tail, d, -0.25 * u)
            out = scale(d, -1)
        cv_.arrow(tail, tip, lw=1.6, head=12, color=color)
        ha, va = align_for(out)
        cv_.text(anchor, f"${pf.label}$", ha=ha, va=va, color=color)

        # Winkelangabe bei schrägen Kräften
        if abs(math.sin(2 * ang)) > 1e-6:
            tail_dir = norm((tail[0] - P[0], tail[1] - P[1]))
            href = (math.copysign(1.0, tail_dir[0]), 0.0)
            alpha = math.degrees(math.acos(min(1.0, abs(tail_dir[0]))))
            r = 1.25 * u
            th0 = math.atan2(href[1], href[0])
            th1 = math.atan2(tail_dir[1], tail_dir[0])
            if th1 - th0 > math.pi:
                th1 -= 2 * math.pi
            elif th0 - th1 > math.pi:
                th1 += 2 * math.pi
            ths = np.linspace(th0, th1, 30)
            cv_.line(P[0] + r * np.cos(ths), P[1] + r * np.sin(ths), lw=0.8, color=color, zorder=3)
            if not any(dot(m, href) > 0.99 for m in dirs):
                e = add(P, href, 1.9 * u)
                cv_.line([P[0], e[0]], [P[1], e[1]], lw=0.7, color=color, linestyle=(0, (1.5, 1.5)))
            mid = 0.5 * (th0 + th1)
            lab = add(P, (math.cos(mid), math.sin(mid)), r + 0.55 * u)
            cv_.text(lab, f"${alpha:.0f}^\\circ$", fs=cv.FONT_SIZE - 1, color=color)


def draw_moments(cv_: Canvas, color=cv.INK):
    geo, u = cv_.geo, cv_.u
    r = 0.85 * u
    for pm in geo.st.point_moments:
        P = geo.at(pm.at)
        ccw = num(pm.m) > 0
        th = np.radians(np.linspace(-60, 240, 60) if ccw else np.linspace(240, -60, 60))
        xs, ys = P[0] + r * np.cos(th), P[1] + r * np.sin(th)
        cv_.line(xs[:-3], ys[:-3], lw=1.5, color=color, zorder=4)
        cv_.arrow((xs[-4], ys[-4]), (xs[-1], ys[-1]), lw=1.5, head=10, color=color)
        cands = [
            add(P, (math.cos(math.radians(a)), math.sin(math.radians(a))), r + 0.6 * u) for a in (50, 130, 90, 20, 160)
        ]
        _place_label(cv_, pm.label, P, cands, fs=cv.FONT_SIZE, color=color)


def draw_loads(cv_: Canvas, color=cv.INK):
    # Einzellasten zuerst, damit die Beschriftung der Streckenlasten ihnen ausweichen kann
    draw_point_forces(cv_, color)
    draw_moments(cv_, color)
    draw_line_loads(cv_, color)
