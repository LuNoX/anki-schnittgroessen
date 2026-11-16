"""Invarianten zur Selbstkontrolle eines gelösten Systems (``tm-anki check``)."""

from __future__ import annotations

import sympy as sp

from .model import SystemDef
from .solver import QUANTITIES, Result
from .symbols import LOAD_SYMBOLS, ZEICHENWERTE, S, num

TOL = 1e-9


def _zero(expr) -> bool:
    return sp.simplify(sp.expand(expr)) == 0


def check(sysdef: SystemDef, result: Result) -> tuple[list[str], list[str]]:
    """(Fehler, Warnungen)."""
    st = result.structure
    errors: list[str] = []
    warnings: list[str] = []

    if sysdef.groessen:
        for g in sysdef.groessen:
            if g not in QUANTITIES:
                errors.append(f"unbekannte Größe {g!r}")

    load_syms = set()
    for pf in st.point_forces:
        load_syms |= pf.magnitude.free_symbols
    for pm in st.point_moments:
        load_syms |= pm.magnitude.free_symbols
    for ll in st.line_loads:
        load_syms |= ll.qa.free_symbols | ll.qb.free_symbols
    load_syms &= set(LOAD_SYMBOLS)
    # Mehrere unabhängige Lasten sind erlaubt (z. B. q_1, q_2), brauchen aber verschiedene Zeichenwerte,
    # sonst zeigt die Zeichnung einen Sonderfall (q_1 = q_2) statt des allgemeinen Falls.
    werte = [ZEICHENWERTE.get(s, 1) for s in load_syms]
    if len(set(werte)) < len(werte):
        warnings.append(
            f"unabhängige Lastsymbole {sorted(map(str, load_syms))} mit gleichem Zeichenwert: "
            "Last über eines ausdrücken (z. B. F = q*a) oder last(..., zeichenwert=...) setzen"
        )

    # globales Gleichgewicht: Lasten + Reaktionen
    fx = fz = mo = sp.S.Zero

    def add(x, z, px, pz, m=0):
        nonlocal fx, fz, mo
        fx += px
        fz += pz
        mo += z * px - x * pz + m

    for pf in st.point_forces:
        x, z = _pos(st, pf.at)
        add(x, z, pf.fx, pf.fz)
    for pm in st.point_moments:
        x, z = _pos(st, pm.at)
        add(x, z, 0, 0, pm.m)
    t = sp.Symbol("t")
    for ll in st.line_loads:
        m = st.members[ll.member]
        w = ll.factor * ll.q_at(t)
        R = sp.integrate(w, (t, ll.sa, ll.sb))
        rx, rz = m.r0[0] + t * m.e1[0], m.r0[1] + t * m.e1[1]
        add(0, 0, R * ll.d[0], R * ll.d[1], sp.integrate((rz * ll.d[0] - rx * ll.d[1]) * w, (t, ll.sa, ll.sb)))
    for rv in result.reactions:
        n = st.nodes[rv.support.node]
        if rv.direction is None:
            add(n.x, n.z, 0, 0, rv.value)
        else:
            add(n.x, n.z, rv.direction[0] * rv.value, rv.direction[1] * rv.value)
    for name, val in (("ΣX", fx), ("ΣZ", fz), ("ΣM", mo)):
        if not _zero(val):
            errors.append(f"Gleichgewicht verletzt: {name} = {sp.simplify(val)}")

    # M2 = 0 an Gelenken
    for h in st.hinges:
        for mr in result.members:
            m = mr.member
            if h == m.n0 and not _zero(mr.segments[0].M2.subs(S, 0)):
                errors.append(f"M2 != 0 am Gelenk {h} (Stab {m.n0}-{m.n1})")
            if h == m.n1 and not _zero(mr.segments[-1].M2.subs(S, m.length)):
                errors.append(f"M2 != 0 am Gelenk {h} (Stab {m.n0}-{m.n1})")

    # freie Enden ohne Knotenmoment: M2 = 0
    moment_nodes = {pm.at.node for pm in st.point_moments if pm.at.node}
    for name in st.nodes:
        ms = st.members_at(name)
        if len(ms) != 1 or st.support_at(name) or name in moment_nodes or name in st.hinges:
            continue
        mr = result.members[ms[0].idx]
        val = mr.segments[0].M2.subs(S, 0) if ms[0].n0 == name else mr.segments[-1].M2.subs(S, ms[0].length)
        if not _zero(val):
            errors.append(f"M2 != 0 am freien Ende {name}")

    # Differentialbeziehungen je Abschnitt: dM2/ds = Q3, dQ3/ds = -q3, dN1/ds = -q1
    for mr in result.members:
        m = mr.member
        for g in mr.segments:
            if not _zero(sp.diff(g.M2, S) - g.Q3):
                errors.append(f"dM2/dx1 != Q3 auf Stab {m.n0}-{m.n1}")
            mid = (g.sa + g.sb) / 2
            q1 = q3 = sp.S.Zero
            for ll in st.line_loads:
                if ll.member == m.idx and num(ll.sa) - TOL <= num(mid) <= num(ll.sb) + TOL:
                    w = ll.factor * ll.q_at(S)
                    q1 += w * (ll.d[0] * m.e1[0] + ll.d[1] * m.e1[1])
                    q3 += w * (ll.d[0] * m.e3[0] + ll.d[1] * m.e3[1])
            if not _zero(sp.diff(g.Q3, S) + q3):
                errors.append(f"dQ3/dx1 != -q3 auf Stab {m.n0}-{m.n1}")
            if not _zero(sp.diff(g.N1, S) + q1):
                errors.append(f"dN1/dx1 != -q1 auf Stab {m.n0}-{m.n1}")

    # Sprünge an Einzellasten im Stabinneren
    for pf in st.point_forces:
        if pf.at.member is None:
            continue
        mr = result.members[pf.at.member]
        m = mr.member
        for qty, e in (("N1", m.e1), ("Q3", m.e3)):
            jump = mr.value(qty, pf.at.s, "right") - mr.value(qty, pf.at.s, "left")
            expected = -(pf.fx * e[0] + pf.fz * e[1])
            if not _zero(jump - expected):
                errors.append(f"Sprung von {qty} an Einzelkraft auf Stab {m.n0}-{m.n1} falsch")
    for pm in st.point_moments:
        if pm.at.member is None:
            continue
        mr = result.members[pm.at.member]
        jump = mr.value("M2", pm.at.s, "right") - mr.value("M2", pm.at.s, "left")
        if not _zero(jump + mr.member.fiber * pm.m):
            errors.append(f"Sprung von M2 am Einzelmoment auf Stab {mr.member.n0}-{mr.member.n1} falsch")

    return errors, warnings


def _pos(st, loc):
    if loc.node is not None:
        n = st.nodes[loc.node]
        return n.x, n.z
    return st.members[loc.member].point(loc.s)
