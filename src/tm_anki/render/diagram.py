"""Schnittgrößenverlauf senkrecht zu den Stäben auf dem Stabskelett."""

from __future__ import annotations

import itertools
import math

import numpy as np
import sympy as sp

from .. import conventions as cv
from ..fmt import DIM_OPS, is_simple, latex_value
from ..fmt import math as fmt_math
from ..keypoints import KeyPoint, extremum_offset
from ..solver import Result
from ..symbols import S, numeric_subs
from .base import Canvas, add, align_for, dot, norm, scale
from .structure import draw_fiber, draw_hinges, draw_members, fiber_polyline

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
            ss = np.linspace(
                float(sp.N(seg.sa.subs(numeric_subs(seg.sa)))), float(sp.N(seg.sb.subs(numeric_subs(seg.sb)))), SAMPLES
            )
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


def draw_diagram(
    cv_: Canvas,
    result: Result,
    qty: str,
    kps: list[KeyPoint],
    visible: bool = True,
    overlay: bool = False,
    avoid_boxes: list | None = None,
    movable_labels: list | None = None,
) -> dict:
    """Verlauf zeichnen. ``overlay=True``: direkt in die Systemzeichnung.

    ``avoid_boxes``: Symbole und Bezeichnungen von Lagern und Lasten; die Werte des Verlaufs weichen
    ihnen aus, die Symbole selbst dürfen aber überdeckt werden. ``movable_labels``: (Text, Box) der
    Bezeichnungen (A, B, F, q, M0 ...); sie werden aus der Verlaufsfläche herausgeschoben.

    Gibt eine Lesbarkeitsmessung zurück: ``cover`` = größter Anteil, zu dem eine Bezeichnung danach noch
    vom Verlauf verdeckt ist; ``label_hits`` = Werte des Verlaufs, die mit einer Bezeichnung kollidieren.
    """
    geo, u = cv_.geo, cv_.u
    color = cv.COLORS[qty]
    side = cv.plot_sign(qty)
    k = diagram_scale(cv_, result, qty)
    vis = {"visible": visible}
    system_boxes = (list(avoid_boxes) if avoid_boxes is not None else list(cv_.boxes)) if overlay else []
    strict: list = []  # Boxen der Bezeichnungen (nach dem Verschieben)
    metric = {"cover": 0.0, "label_hits": 0}
    polys: list[np.ndarray] = []
    poly_owner: list[tuple] = []  # (Stab, sa, sb) je Verlaufsfläche

    name = f"${cv.LATEX[qty]}$"
    if geo.H < 1e-9 and not overlay:  # Balken: Name links neben der Stabachse
        cv_.text((geo.x0 - 1.3 * u, geo.y0), name, fs=cv.FONT_SIZE + 3, ha="right", occupy=False)

    if k == 0.0:
        cv_.text((0.5 * (geo.x0 + geo.x1), geo.y0 - 1.2 * u), f"{name[:-1]} \\equiv 0$", va="top", **vis)
    else:
        obstacles: list = []  # Stabachsen, Faser und Verlaufslinien (für die Platzierung der Werte)
        for g in geo.members:
            n = max(2, int(g.L / (0.15 * u)))
            obstacles += [g.point(s) for s in np.linspace(0, g.L, n)]
        for chain in geo.st.chains:
            pts = fiber_polyline(geo, chain, 0.36 * u)
            for p, q_ in itertools.pairwise(pts):
                n = max(2, int(math.dist(p, q_) / (0.15 * u)))
                obstacles += [add(p, (q_[0] - p[0], q_[1] - p[1]), t) for t in np.linspace(0, 1, n)]
        placed_markers: list = []  # über alle Stabzüge, damit sich Marker nicht überdecken
        for chain in geo.st.chains:
            obstacles += _draw_chain(cv_, result, qty, chain, k, side, color, vis, placed_markers, polys, poly_owner)
        fill = _fill_samples(geo, result, qty, k, side)
        if overlay and movable_labels:
            strict = _move_labels_out(cv_, movable_labels, polys, system_boxes)
            if polys:
                metric["cover"] = _max_box_cover(strict, polys, min_area=0.0)
        if overlay:  # Dreibein und Bemaßungskette sollen danach um den Verlauf herum platziert werden
            cv_.obstacle_pts = np.vstack([fill, np.array(obstacles).reshape(-1, 2)])
        metric["label_hits"] = _place_value_labels(
            cv_,
            result,
            qty,
            kps,
            k,
            side,
            vis,
            np.array(obstacles),
            system_boxes,
            strict if overlay else None,
            list(zip(polys, poly_owner)),
        )

    if geo.H >= 1e-9 and not overlay:  # Rahmen: Name oben links über dem Verlauf
        cv_.text((cv_.ext[0], cv_.ext[3] + 0.3 * u), name, fs=cv.FONT_SIZE + 3, ha="left", va="bottom", occupy=False)
    return metric


def _fill_samples(geo, result: Result, qty: str, k: float, side: int) -> np.ndarray:
    """Stichproben der Verlaufsfläche (zwischen Stabachse und Kurve)."""
    pts = []
    for mr in result.members:
        g = geo.members[mr.member.idx]
        for seg in mr.segments:
            ss = np.linspace(_num(seg.sa), _num(seg.sb), 24)
            vs = _lam(seg.f(qty))(ss)
            for s, v in zip(ss, vs):
                if abs(v) * k < 1e-9:
                    continue
                for frac in (0.25, 0.5, 0.75, 1.0):
                    pts.append(add(g.point(s), g.e3, side * v * k * frac))
    return np.array(pts).reshape(-1, 2)


def _move_labels_out(cv_: Canvas, labels: list, polys: list[np.ndarray], system_boxes: list) -> list:
    """Bezeichnungen, die in einer Verlaufsfläche liegen, vom Tragwerk weg nach außen schieben, bis sie frei
    sind (höchstens ~4u). Aktualisiert Text, Belegung und ``system_boxes``; gibt die neuen Boxen zurück."""
    from matplotlib.path import Path

    geo, u = cv_.geo, cv_.u
    paths = [Path(p) for p in polys if len(p) >= 3]

    def covered(box) -> bool:
        m = 0.12 * u  # etwas Abstand zur Kurve
        gx, gy = np.meshgrid(np.linspace(box[0] - m, box[2] + m, 5), np.linspace(box[1] - m, box[3] + m, 5))
        grid = np.column_stack([gx.ravel(), gy.ravel()])
        return any(path.contains_points(grid).any() for path in paths)

    member_pts = np.array([g.point(s) for g in geo.members for s in np.linspace(0, g.L, max(2, int(g.L / (0.1 * u))))])

    def on_member(box) -> bool:
        m = 0.1 * u
        return bool(
            np.any(
                (member_pts[:, 0] > box[0] - m)
                & (member_pts[:, 0] < box[2] + m)
                & (member_pts[:, 1] > box[1] - m)
                & (member_pts[:, 1] < box[3] + m)
            )
        )

    out_boxes: list = []
    for art, box in labels:
        if not covered(box):
            out_boxes.append(box)
            continue
        c = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        nearest = min(
            (g.point(min(max(dot((c[0] - g.p0[0], c[1] - g.p0[1]), g.e1), 0.0), g.L)) for g in geo.members),
            key=lambda p: math.dist(p, c),
        )
        d = norm((c[0] - nearest[0], c[1] - nearest[1]))
        if d == (0.0, 0.0):
            d = (0.0, 1.0)
        # nächster freier Platz ringförmig um die ursprüngliche Lage (bei gleichem Abstand: weg vom Tragwerk)
        new = box
        dirs = [(math.cos(t), math.sin(t)) for t in np.linspace(0, 2 * math.pi, 16, endpoint=False)]
        dirs.sort(key=lambda e: -dot(e, d))
        found = False
        for step in range(1, 15):
            for e in dirs:
                dx, dy = e[0] * step * 0.3 * u, e[1] * step * 0.3 * u
                trial = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
                if not covered(trial) and not on_member(trial) and not _box_hits(trial, out_boxes):
                    new, found = trial, True
                    break
            if found:
                break
        if new is not box:
            dx, dy = new[0] - box[0], new[1] - box[1]
            x, y = art.get_position()
            art.set_position((x + dx, y + dy))
            cv_.grow([new[0], new[2]], [new[1], new[3]])
            for lst in (cv_.boxes, system_boxes):
                if box in lst:
                    lst[lst.index(box)] = new
        out_boxes.append(new)
    return out_boxes


def _max_box_cover(boxes: list, polys: list[np.ndarray], min_area: float) -> float:
    """Größter Anteil einer Box (Last-/Lagerelement), der von Verlaufsflächen bedeckt ist."""
    from matplotlib.path import Path

    paths = [Path(p) for p in polys if len(p) >= 3]
    worst = 0.0
    for x0, y0, x1, y1 in boxes:
        if (x1 - x0) * (y1 - y0) < min_area:
            continue
        gx, gy = np.meshgrid(np.linspace(x0, x1, 7), np.linspace(y0, y1, 7))
        grid = np.column_stack([gx.ravel(), gy.ravel()])
        inside = np.zeros(len(grid), dtype=bool)
        for path in paths:
            inside |= path.contains_points(grid)
        worst = max(worst, float(inside.mean()))
    return worst


def _inside_any(pts: np.ndarray, boxes: list) -> np.ndarray:
    hit = np.zeros(len(pts), dtype=bool)
    for x0, y0, x1, y1 in boxes:
        hit |= (pts[:, 0] > x0) & (pts[:, 0] < x1) & (pts[:, 1] > y0) & (pts[:, 1] < y1)
    return hit


def _box_hits(box, boxes: list) -> int:
    return sum(1 for b in boxes if box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1])


def _draw_chain(
    cv_: Canvas,
    result: Result,
    qty: str,
    chain,
    k,
    side,
    color,
    vis,
    placed_markers: list,
    polys: list | None = None,
    poly_owner: list | None = None,
):
    """``polys``/``poly_owner``: Verlaufsflächen und ihr Abschnitt (Stab, sa, sb) werden ergänzt."""
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
        if polys is not None:
            polys.append(np.array(axis + curve[::-1]))
            if poly_owner is not None:
                poly_owner.append((g.idx, sa, sb))
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
    xs = np.concatenate([[0.0], np.cumsum([math.dist(p, q) for p, q in itertools.pairwise(pts)])])
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
                cv_.ax.text(
                    p[0],
                    p[1],
                    txt,
                    fontsize=8,
                    ha="center",
                    va="center",
                    color=cv.INK,
                    zorder=5,
                    bbox={"boxstyle": "circle,pad=0.12", "fc": "white", "ec": color, "lw": 0.9},
                    **vis,
                )
                centers.append(p)
                placed.append(p)

            def free(p):
                return all(math.dist(p, m) >= 1.0 * u for m in placed)

            # innen an einer dicken Stelle, mit Abstand zu den Bereichsrändern und eher zur Mitte hin,
            # und nicht auf einem schon gesetzten Marker (z. B. an T-Anschlüssen)
            x_mid = 0.5 * (xs[i] + xs[j])
            inner = [t for t in range(i, j + 1) if xs[i] + 0.2 * length <= xs[t] <= xs[j] - 0.2 * length]
            ranked = sorted(
                inner or range(i, j + 1), key=lambda t: -abs(vs[t]) * (1 - 0.6 * abs(xs[t] - x_mid) / length)
            )
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


def _place_value_labels(
    cv_: Canvas,
    result: Result,
    qty: str,
    kps: list[KeyPoint],
    k,
    side,
    vis,
    obstacles: np.ndarray,
    avoid: list | None = None,
    strict: list | None = None,
    areas: list | None = None,
) -> int:
    """Werte, Kurvenform und Extremum-Bemaßungen platzieren. ``avoid``: Boxen der Systemzeichnung
    (Lasten, Lager), wenn der Verlauf im System liegt; ``areas``: [(Fläche, (Stab, sa, sb))] der Verläufe.
    Rückgabe: Anzahl verbleibender Kollisionen mit Bezeichnungen."""
    from matplotlib.path import Path

    geo, u = cv_.geo, cv_.u
    fs = cv.VALUE_FONT_SIZE
    placed: list[tuple[float, float, float, float]] = []
    avoid = avoid or []
    # Werte halten deutlichen Abstand zu Bezeichnungen (sonst liest man z. B. "B qa" oder "M0 -M0/2" als
    # einen Ausdruck); Symbolen weichen sie nur schwach aus, die dürfen im System überdeckt werden.
    label_gap = 0.3 * u
    labels_gap = [(b[0] - label_gap, b[1] - label_gap, b[2] + label_gap, b[3] + label_gap) for b in (strict or [])]
    symbols = [b for b in avoid if b not in (strict or [])]
    text_pad = 0.08 * u
    area_paths = [(Path(p), owner) for p, owner in (areas or []) if len(p) >= 3]
    dims = np.zeros((0, 2))

    def foreign(box, own: list) -> int:
        """Rasterpunkte der Box in Verlaufsflächen anderer Abschnitte (eigene: [(Stab, s)])."""
        gx, gy = np.meshgrid(np.linspace(box[0], box[2], 4), np.linspace(box[1], box[3], 4))
        grid = np.column_stack([gx.ravel(), gy.ravel()])
        hit = np.zeros(len(grid), dtype=bool)
        for path, (mi, sa, sb) in area_paths:
            if any(mi == m and sa - 1e-6 <= s <= sb + 1e-6 for m, s in own):
                continue
            hit |= path.contains_points(grid)
        return int(hit.sum())

    def score(box, own: list | None = None) -> float:
        x0, y0, x1, y1 = box[0] - text_pad, box[1] - text_pad, box[2] + text_pad, box[3] + text_pad
        inside = 0
        if len(obstacles):
            inside = int(
                np.count_nonzero(
                    (obstacles[:, 0] > x0) & (obstacles[:, 0] < x1) & (obstacles[:, 1] > y0) & (obstacles[:, 1] < y1)
                )
            )
        on_dim = 0
        if len(dims):  # Maß- und Hilfslinien der Extremum-Bemaßung: nie durch einen Wert hindurch
            on_dim = int(
                np.count_nonzero((dims[:, 0] > x0) & (dims[:, 0] < x1) & (dims[:, 1] > y0) & (dims[:, 1] < y1))
            )
        sc = inside + 8 * on_dim + 50 * _box_hits(box, placed) + 30 * _box_hits(box, labels_gap)
        sc += 4 * _box_hits(box, symbols)
        if own is not None and area_paths:
            sc += 3 * foreign(box, own)  # nicht in der Schraffur eines anderen Abschnitts
        return sc

    # Lage der Extrema als Bemaßung direkt am Stab, gemessen ab Beginn des Teilbereichs
    dim_pts = _draw_extremum_dimensions(cv_, result, qty, kps, k, side, vis, placed, avoid)
    if dim_pts:
        dims = np.array(dim_pts)

    for kp in kps:
        if not is_simple(kp.value):  # unhandlicher Ausdruck (z. B. allgemeine Trapezlast): nicht angeben
            continue
        v = _num(kp.value)
        text = fmt_math(kp.value)
        if cv.VALUE_FULL_SIZE_FRACTIONS:
            text = text.replace("\\frac", "\\dfrac")
        best = None
        for mi, s_expr in [(kp.member, kp.s), *kp.alts]:
            s_c = _num(s_expr)
            own = [(mi, s_c)] + ([(kp.member2, 0.0)] if kp.kind == "ecke" and kp.member2 is not None else [])
            base = _label_anchor(geo, kp, mi, s_c, v, k, side, u)
            g_m = geo.members[mi]
            e1 = g_m.e1
            # eigener Abschnitt liegt in Richtung own_dir entlang e1: dorthin ausweichen ist billiger als
            # über einen Sprung hinweg in den Nachbarabschnitt
            own_dir = {"left": -1, "right": 1}.get(kp.side, 0)
            if own_dir == 0 and kp.kind == "rand":
                own_dir = 1 if s_c < 1e-9 else (-1 if s_c > g_m.L - 1e-9 else 0)
            cands = [
                (add(base[0], e1, sh * u), *base[1:], sh) for sh in (0.0, 0.55, -0.55, 1.1, -1.1, 1.8, -1.8, 2.6, -2.6)
            ]
            if kp.kind == "ecke" and kp.member2 is not None:
                # in die freie Ecke zwischen den beiden Ordinaten (Bezugspunkt der Ecke: ref)
                P, ref = g_m.point(s_c), base[4]
                cands.insert(0, (add(P, (ref[0] - P[0], ref[1] - P[1]), 0.5), "center", "center", *base[3:], 0.0))
            for anchor_c, ha_c, va_c, out_c, c_c, g_c, s_cc, sh in cands:
                box = cv_.text_box(anchor_c, text, fs, ha_c, va_c)
                penalty = 0.5 * abs(sh) / 0.55 * (3 if sh * own_dir < 0 else 1)
                sc = score(box, own) + penalty
                if sh == 0.0 and ha_c == "center" and va_c == "center" and kp.kind == "ecke":
                    sc += 3 * foreign(box, [])  # Eckposition nur, wenn sie außerhalb aller Flächen liegt
                if best is None or sc < best[0]:
                    best = (sc, (anchor_c, ha_c, va_c, out_c, c_c, g_c, s_cc), box, own)
            if best[0] == 0:
                break
        _, (anchor, ha, va, out, c, g, s), box, own = best
        sc = score(box, own)
        for _ in range(8):  # noch Konflikt (z. B. in fremder Schraffur): nach außen schieben, wenn es hilft
            if sc == 0:
                break
            trial = add(anchor, out, 0.3 * u)
            tbox = cv_.text_box(trial, text, fs, ha, va)
            tsc = score(tbox, own)
            if tsc < sc:
                anchor, box, sc = trial, tbox, tsc
            else:
                break
        if kp.kind == "extrem":
            p = g.point(s)
            cv_.line(
                [p[0], c[0]],
                [p[1], c[1]],
                occupy=False,
                color=cv.INK_MUTED,
                lw=0.7,
                linestyle=(0, (1.5, 1.5)),
                zorder=2,
                **vis,
            )
            cv_.circle(c, 0.07 * u, occupy=False, fc=cv.INK, ec="none", zorder=4, **vis)
        # deutlich vom Kurvenpunkt abgerückt: feine Führungslinie zeigt, wohin der Wert gehört
        near = (min(max(c[0], box[0]), box[2]), min(max(c[1], box[1]), box[3]))
        in_notch = False
        if kp.kind == "ecke":  # Wert steht in der Ecke zwischen den beiden Ordinaten: keine Führungslinie
            P = g.point(s)
            notch = (min(P[0], c[0]), min(P[1], c[1]), max(P[0], c[0]), max(P[1], c[1]))
            in_notch = bool(_box_hits(box, [notch]))
        if math.dist(near, c) > 0.6 * u and not in_notch:
            tip = add(c, norm((near[0] - c[0], near[1] - c[1])), 0.08 * u)
            cv_.line([tip[0], near[0]], [tip[1], near[1]], occupy=False, color=cv.INK_MUTED, lw=0.6, zorder=5, **vis)
        placed.append(box)
        cv_.text(anchor, text, fs=fs, ha=ha, va=va, occupy=False, zorder=6, **vis)

    # Kurvenform direkt an der Kurve (kurz, z. B. "quadr."), je Teilbereich, nach den Werten platziert.
    # Gesucht wird entlang des Bereichs und mit wachsendem Abstand nach außen: Kollisionen (auch mit
    # Lastpfeilen) kosten viel, Abstand und Randlage wenig -> lieber weiter außen als im Pfeilfeld.
    fs_c = cv.CURVE_FONT_SIZE
    for mr in result.members:
        g = geo.members[mr.member.idx]
        for seg in mr.segments:
            f = sp.expand(seg.f(qty))
            degree = sp.degree(f, S) if S in f.free_symbols else 0
            if degree < 2:
                continue
            text = cv.CURVE_LABELS.get(degree, f"Grad {degree}")
            lam = _lam(f)
            sa, sb = _num(seg.sa), _num(seg.sb)
            best = None
            for frac in (0.5, 0.35, 0.65, 0.25, 0.75, 0.15, 0.85):
                s = sa + frac * (sb - sa)
                v = float(lam(np.array(s)))
                if abs(v) * k < 1e-9:
                    continue
                out = scale(g.e3, side * math.copysign(1.0, v))
                ha, va = align_for(out)
                for off in (0.22, 0.6, 1.0, 1.5, 2.1, 2.8):
                    anchor = add(add(g.point(s), g.e3, side * v * k), out, off * u)
                    box = cv_.text_box(anchor, text, fs_c, ha, va)
                    cost = 10 * score(box, [(g.idx, s)]) + off + 2 * abs(frac - 0.5)
                    if best is None or cost < best[0]:
                        best = (cost, anchor, ha, va, box)
            if best is None:
                continue
            _, anchor, ha, va, box = best
            placed.append(box)
            cv_.text(
                anchor,
                text,
                fs=fs_c,
                ha=ha,
                va=va,
                occupy=False,
                zorder=6,
                color=cv.INK_MUTED,
                fontstyle="italic",
                **vis,
            )
    cv_.boxes.extend(placed)  # Werte, Kurvenlabels, Bemaßungszahlen: Dreibein und Maßkette weichen aus
    if len(dims):
        cv_.obstacle_pts = np.vstack([cv_.obstacle_pts.reshape(-1, 2), dims])
    return sum(1 for b in placed if _box_hits(b, strict if strict is not None else avoid))


def _draw_extremum_dimensions(
    cv_: Canvas, result: Result, qty: str, kps: list[KeyPoint], k: float, side: int, vis, placed: list, avoid: list
):
    """Bemaßung vom Beginn des Teilbereichs bis zum Extremum, bevorzugt auf der dem Verlauf abgewandten
    Seite; liegen dort Lasten oder Lager (Verlauf im System), weiter außen oder jenseits der Kurve.
    Gibt Punkte entlang der Bemaßung zurück (Hindernisse für weitere Beschriftungen)."""
    geo, u = cv_.geo, cv_.u
    fs = cv.FONT_SIZE
    pts = []
    for kp in kps:
        if kp.kind != "extrem" or not is_simple(kp.value):
            continue
        seg = next(
            g for g in result.members[kp.member].segments if _num(g.sa) - 1e-9 <= _num(kp.s) <= _num(g.sb) + 1e-9
        )
        dist = extremum_offset(result, kp)
        if not is_simple(dist, DIM_OPS):  # Lage zu unhandlich für eine Bemaßung
            continue
        g = geo.members[kp.member]
        s0, s1 = _num(seg.sa), _num(kp.s)
        a0, a1 = g.point(s0), g.point(s1)
        text = f"${latex_value(dist)}$".replace("\\frac", "\\dfrac")

        # Kandidaten: Gegenseite (nah -> weiter außen), dann jenseits der Kurve
        n_opp = scale(g.e3, -side * math.copysign(1.0, _num(kp.value)))
        n_cur = scale(n_opp, -1)
        base = (0.85 if dot(n_opp, g.e3) > 0 else 0.6) * u  # auf der Faserseite etwas weiter weg
        ss = np.linspace(s0, s1, 16)
        reach = float(np.max(np.abs(_lam(seg.f(qty))(ss)))) * k
        cands = [(n_opp, base + extra * u) for extra in (0, 0.6, 1.2, 1.8, 2.6, 3.4)]
        cands += [(n_cur, reach + extra * u) for extra in (0.7, 1.3, 2.0)]
        pad = 0.2 * u  # Abstand zu Lasten/Lagern, damit sich die Bemaßung nicht dazwischen quetscht
        avoid_pad = [(b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad) for b in avoid]
        lam = _lam(seg.f(qty))
        best = None
        for n, off in cands:
            p0, p1 = add(a0, n, off), add(a1, n, off)
            line = np.array([add(p0, (p1[0] - p0[0], p1[1] - p0[1]), t) for t in np.linspace(0, 1, 30)])
            # Hilfslinien: auf der Kurvenseite erst an der Kurve beginnen (nicht quer durch die Fläche)
            if dot(n, n_cur) > 0:
                starts = [add(a, n, abs(float(lam(np.array(s)))) * k + 0.1 * u) for a, s in ((a0, s0), (a1, s1))]
            else:
                starts = [a0, a1]
            mid = add(p0, (p1[0] - p0[0], p1[1] - p0[1]), 0.5)
            ha, va = align_for(n)
            anchor = add(mid, n, 0.14 * u)
            box = cv_.text_box(anchor, text, fs, ha, va)
            for _ in range(12):  # Zahl so weit abrücken, dass sie die (evtl. schräge) Maßlinie nicht schneidet
                if not np.any(_inside_any(line, [box])):
                    break
                anchor = add(anchor, n, 0.1 * u)
                box = cv_.text_box(anchor, text, fs, ha, va)
            helpers = np.array(
                [
                    add(a, (p[0] - a[0], p[1] - a[1]), t)  # Hilfslinien zur Maßlinie
                    for a, p in zip(starts, (p0, p1))
                    for t in np.linspace(0, 1, 16)
                ]
            )
            hits = (
                int(np.count_nonzero(_inside_any(np.vstack([line, helpers]), avoid_pad)))
                + 10 * _box_hits(box, avoid_pad)
                + 10 * _box_hits(box, placed)
            )
            sc = 10 * hits + off / u  # Kollisionen vermeiden, sonst möglichst nah am Stab
            if best is None or sc < best[0]:
                best = (sc, n, p0, p1, anchor, ha, va, box, np.vstack([line, helpers]), starts)
        _, n, p0, p1, anchor, ha, va, box, line, starts = best
        style = dict(occupy=False, color=cv.INK_MUTED, zorder=2, **vis)
        cv_.line([p0[0], p1[0]], [p0[1], p1[1]], lw=0.8, **style)
        tick = norm(add(g.e1, n))
        for a, p in zip(starts, (p0, p1)):
            e = add(p, n, 0.15 * u)
            cv_.line([a[0], e[0]], [a[1], e[1]], lw=0.6, **style)  # Hilfslinie
            t0, t1 = add(p, tick, -0.17 * u), add(p, tick, 0.17 * u)
            cv_.line([t0[0], t1[0]], [t0[1], t1[1]], lw=0.9, **style)
        placed.append(box)
        cv_.text(anchor, text, fs=fs, ha=ha, va=va, occupy=False, zorder=6, **vis)
        pts += [tuple(p) for p in line]
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
        c = diag  # Bezugspunkt des Eckwerts ist die Ecke der beiden Ordinaten
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
