"""Kennwerte eines Verlaufs: Werte an Rändern/Sprüngen, konstante Bereiche, Extrema."""

from __future__ import annotations

from dataclasses import dataclass, field

import sympy as sp

from .fmt import simplify_radicals
from .solver import Result, Segment
from .symbols import S, num, numeric_subs

TOL = 1e-9


@dataclass
class KeyPoint:
    member: int
    s: sp.Expr  # lokale Koordinate
    value: sp.Expr
    kind: str  # "rand" | "extrem" | "konst" | "ecke" (stetiger Wert an einer biegesteifen Ecke)
    side: str  # "left" | "right" | "mid"  (bei Sprüngen: Grenzwert von links/rechts)
    x1: sp.Expr  # Bogenlänge entlang des Stabzugs
    chain: int
    member2: int | None = None  # bei "ecke": anschließender Stab
    alts: list = field(default_factory=list)  # bei "konst": Ausweichpositionen [(Stab, s)]


def _is_const(f: sp.Expr) -> bool:
    return S not in sp.sympify(f).free_symbols


def _at(f: sp.Expr, s) -> sp.Expr:
    return sp.simplify(sp.sympify(f).subs(S, s))


def _nonzero(v) -> bool:
    return abs(num(v)) > TOL


def _same(v, w) -> bool:
    return abs(num(v) - num(w)) < TOL


def extrema(f: sp.Expr, sa, sb) -> list[sp.Expr]:
    """Innere Nullstellen der Ableitung (exakt)."""
    if _is_const(f):
        return []
    d = sp.diff(f, S)
    if _is_const(d):
        return []
    roots = []
    lo, hi = num(sa), num(sb)
    for r in sp.solve(sp.Eq(d, 0), S):
        r_num = complex(r.subs(numeric_subs(r)))
        if abs(r_num.imag) < TOL and lo + TOL < r_num.real < hi - TOL:
            roots.append(simplify_radicals(r))
    return roots


def extremum_offset(result: Result, kp: KeyPoint) -> sp.Expr:
    """Abstand eines Extremums vom Beginn seines Teilbereichs (für die Bemaßung)."""
    seg = next(g for g in result.members[kp.member].segments if num(g.sa) - TOL <= num(kp.s) <= num(g.sb) + TOL)
    return simplify_radicals(kp.s - seg.sa)


def keypoints(result: Result, qty: str) -> list[KeyPoint]:
    st = result.structure
    out: list[KeyPoint] = []
    for chain in st.chains:
        segs: list[tuple[int, Segment]] = []
        for mi in chain.members:
            segs += [(mi, g) for g in result.members[mi].segments]

        def kp(mi, s, v, kind, side, member2=None):
            m = st.members[mi]
            out.append(
                KeyPoint(mi, sp.simplify(s), sp.simplify(v), kind, side, sp.simplify(m.s0 + s), chain.idx, member2)
            )

        def collinear(m1: int, m2: int) -> bool:
            e, f_ = st.members[m1].e1, st.members[m2].e1
            return m1 == m2 or (abs(num(e[0]) - num(f_[0])) < TOL and abs(num(e[1]) - num(f_[1])) < TOL)

        i = 0
        while i < len(segs):
            mi, g = segs[i]
            f = g.f(qty)
            if not _is_const(f):
                for r in extrema(f, g.sa, g.sb):
                    v = simplify_radicals(sp.sympify(f).subs(S, r))
                    if _nonzero(v):
                        kp(mi, r, v, "extrem", "mid")
                i += 1
                continue
            # zusammenhängender konstanter Bereich (auch über Gelenke/Knoten) -> ein Label in der Mitte
            j = i
            while (
                j + 1 < len(segs)
                and _is_const(segs[j + 1][1].f(qty))
                and _same(segs[j + 1][1].f(qty), f)
                and collinear(segs[j][0], segs[j + 1][0])
            ):
                j += 1
            if _nonzero(f):
                x_lo = st.members[mi].s0 + g.sa
                x_hi = st.members[segs[j][0]].s0 + segs[j][1].sb
                spots = []
                for frac in (
                    sp.Rational(1, 2),
                    sp.Rational(3, 10),
                    sp.Rational(7, 10),
                    sp.Rational(1, 5),
                    sp.Rational(4, 5),
                ):
                    x = x_lo + frac * (x_hi - x_lo)
                    for mk, gk in segs[i : j + 1]:
                        s0 = st.members[mk].s0
                        if num(s0 + gk.sa) - TOL <= num(x) <= num(s0 + gk.sb) + TOL:
                            spots.append((mk, sp.simplify(x - s0)))
                            break
                kp(*spots[0], f, "konst", "mid")
                out[-1].alts = spots[1:]
            i = j + 1

        # Ränder und Übergänge
        for i in range(len(segs) + 1):
            left = segs[i - 1] if i > 0 else None
            right = segs[i] if i < len(segs) else None
            lv = _at(left[1].f(qty), left[1].sb) if left else None
            rv = _at(right[1].f(qty), right[1].sa) if right else None
            l_const = left is not None and _is_const(left[1].f(qty))
            r_const = right is not None and _is_const(right[1].f(qty))
            if left and right and _same(lv, rv):
                if not (l_const or r_const) and _nonzero(lv):
                    if collinear(left[0], right[0]):
                        kp(left[0], left[1].sb, lv, "rand", "mid")
                    else:
                        kp(left[0], left[1].sb, lv, "ecke", "mid", member2=right[0])
                continue
            only_one = left is None or right is None
            if left and not l_const and _nonzero(lv):
                kp(left[0], left[1].sb, lv, "rand", "mid" if only_one else "left")
            if right and not r_const and _nonzero(rv):
                kp(right[0], right[1].sa, rv, "rand", "mid" if only_one else "right")

    # gleicher Wert am gleichen Punkt aus verschiedenen Stabzügen (z. B. Knoten mit Abzweig) nur einmal
    unique: list[KeyPoint] = []
    seen: set[tuple[float, float, float]] = set()
    for k in out:
        x, z = st.members[k.member].point(k.s)
        key = (round(num(x), 6), round(num(z), 6), round(num(k.value), 9))
        if k.kind in ("rand", "ecke") and key in seen:
            continue
        seen.add(key)
        unique.append(k)
    return unique


CURVE_NAMES = {2: "quadratische Parabel", 3: "kubische Parabel"}


def curve_name(degree: int) -> str:
    return CURVE_NAMES.get(degree, f"Polynom {degree}. Grades")


@dataclass
class CurveRange:
    """Zusammenhängender Bereich gleicher Kurvenform (Grad >= 2) entlang eines Stabzugs."""

    degree: int
    members: list[int]  # beteiligte (kollineare) Stäbe in Laufrichtung
    s_lo: sp.Expr  # Start, gemessen vom Anfang des ersten Stabs
    s_hi: sp.Expr  # Ende, gemessen vom Anfang des ersten Stabs
    x1_lo: sp.Expr  # Bogenlänge entlang des Stabzugs
    x1_hi: sp.Expr
    full: bool  # deckt die beteiligten Stäbe vollständig ab
    expr_x1: sp.Expr = sp.S.Zero  # Verlauf als Funktion der Bogenlänge (zum Zusammenfassen)

    @property
    def name(self) -> str:
        return curve_name(self.degree)


def curve_forms(result: Result, qty: str) -> list[CurveRange]:
    """Bereiche, in denen der Verlauf weder null, konstant noch linear ist.

    Aufeinanderfolgende Abschnitte werden nur zusammengefasst, wenn sich dieselbe Funktion fortsetzt
    (z. B. über ein Gelenk ohne Einzellast), nicht bloß derselbe Grad (zwei verschiedene Parabeln).
    """
    st = result.structure
    out: list[CurveRange] = []
    x = sp.Symbol("x1")
    for chain in st.chains:
        cur = None
        for mi in chain.members:
            m = st.members[mi]
            for g in result.members[mi].segments:
                f = sp.expand(g.f(qty))
                deg = sp.degree(f, S) if S in f.free_symbols else 0
                x_lo, x_hi = sp.simplify(m.s0 + g.sa), sp.simplify(m.s0 + g.sb)
                if deg < 2:
                    cur = None
                    continue
                f_x = sp.expand(f.subs(S, x - m.s0))
                first = st.members[cur.members[0]] if cur else None
                if (
                    cur
                    and _same(cur.x1_hi, x_lo)
                    and sp.expand(cur.expr_x1 - f_x) == 0
                    and abs(num(first.e1[0]) - num(m.e1[0])) < TOL
                    and abs(num(first.e1[1]) - num(m.e1[1])) < TOL
                ):
                    if mi not in cur.members:
                        cur.members.append(mi)
                    cur.x1_hi = x_hi
                    cur.s_hi = sp.simplify(x_hi - first.s0)
                else:
                    cur = CurveRange(deg, [mi], g.sa, g.sb, x_lo, x_hi, False, f_x)
                    out.append(cur)
    for c in out:
        total = sum((st.members[mi].length for mi in c.members), sp.S.Zero)
        c.full = _same(c.s_lo, 0) and _same(c.s_hi, total)
    return out


def extremes(kps: list[KeyPoint]) -> tuple[KeyPoint | None, KeyPoint | None]:
    """Größter positiver und kleinster negativer Kennwert."""
    pos = [k for k in kps if num(k.value) > TOL]
    neg = [k for k in kps if num(k.value) < -TOL]
    best_pos = max(pos, key=lambda k: num(k.value)) if pos else None
    best_neg = min(neg, key=lambda k: num(k.value)) if neg else None
    return best_pos, best_neg
