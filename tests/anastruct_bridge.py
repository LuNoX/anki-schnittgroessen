"""Übersetzt ein Structure-Objekt nach anaStruct (2D-FEM) zur unabhängigen Gegenrechnung.

Elemente werden in Laufrichtung (x1) angelegt und an allen Lastgrenzen geteilt.
Vorzeichenabbildung (an EF04/KA01/EF11/Winkelträger kalibriert, s. test_orakel_anastruct.py):
    N_ana = SIGN_N * N1,   Q_ana = SIGN_Q * fiber * Q3,   M_ana = SIGN_M * fiber * M2
"""

from __future__ import annotations

import itertools
from typing import Literal

import numpy as np
import sympy as sp
from anastruct import SystemElements

from tm_anki.model import Structure
from tm_anki.solver import Result
from tm_anki.symbols import S, num, numeric_subs

SIGN_N = 1
SIGN_Q = -1
SIGN_M = -1
SIGN_MOMENT_LOAD = 1
SIGN_Q_LOAD = 1
MESH = 21
TOL = 1e-9


class Unsupported(Exception):
    pass


def _breakpoints(st: Structure, mi: int) -> list[float]:
    m = st.members[mi]
    bps = [0.0, num(m.length)]
    for pf in st.point_forces:
        if pf.at.member == mi:
            bps.append(num(pf.at.s))
    for pm in st.point_moments:
        if pm.at.member == mi:
            bps.append(num(pm.at.s))
    for ll in st.line_loads:
        if ll.member == mi:
            bps += [num(ll.sa), num(ll.sb)]
    out: list[float] = []
    for b in sorted(bps):
        if not out or b - out[-1] > TOL:
            out.append(b)
    return out


def _xy(m, s: float) -> list[float]:
    x, z = m.point(sp.Float(s))
    return [num(x), -num(z)]


def build(st: Structure, result: Result):
    ss = SystemElements(EA=1e6, EI=1e4, mesh=MESH)
    body_of = {mi: b for b, mids in enumerate(result.bodies) for mi in mids}
    first_body = {h: min(body_of[m.idx] for m in st.members_at(h)) for h in st.hinges}
    elements = []  # (member, sa, sb, element_id)
    for m in st.members:
        bps = _breakpoints(st, m.idx)
        L = num(m.length)
        for sa, sb in itertools.pairwise(bps):
            spring: dict[Literal[1, 2], float] = {}
            if sa < TOL and m.n0 in first_body and body_of[m.idx] != first_body[m.n0]:
                spring[1] = 0
            if sb > L - TOL and m.n1 in first_body and body_of[m.idx] != first_body[m.n1]:
                spring[2] = 0
            eid = ss.add_element([_xy(m, sa), _xy(m, sb)], spring=spring or None)
            elements.append((m, sa, sb, eid))

    def node_id(x: float, y: float) -> int:
        for nid, node in ss.node_map.items():
            if abs(node.vertex.x - x) < 1e-7 and abs(node.vertex.y - y) < 1e-7:
                return nid
        raise KeyError((x, y))

    def nid_of(loc) -> int:
        if loc.node is not None:
            n = st.nodes[loc.node]
            return node_id(num(n.x), -num(n.z))
        m = st.members[loc.member]
        return node_id(*_xy(m, num(loc.s)))

    for sup in st.supports:
        n = st.nodes[sup.node]
        nid = node_id(num(n.x), -num(n.z))
        if sup.kind == "fest":
            ss.add_support_hinged(nid)
        elif sup.kind == "einspannung":
            ss.add_support_fixed(nid)
        elif sup.kind == "los":
            ang = (90.0 if sup.angle_deg is None else sup.angle_deg) % 180
            if abs(ang - 90) < 1e-9:
                ss.add_support_roll(nid, direction="x")
            elif abs(ang) < 1e-9:
                ss.add_support_roll(nid, direction="y")
            else:
                raise Unsupported("schräges Loslager")

    for pf in st.point_forces:
        ss.point_load(nid_of(pf.at), Fx=num(pf.fx), Fy=-num(pf.fz))
    for pm in st.point_moments:
        ss.moment_load(nid_of(pm.at), Tz=SIGN_MOMENT_LOAD * num(pm.m))

    for ll in st.line_loads:
        m = st.members[ll.member]
        dx, dz = (num(c) for c in ll.d)
        direction: Literal["x", "y"]
        if abs(dx) < TOL:
            direction, sign = "y", -np.sign(dz)
        elif abs(dz) < TOL:
            direction, sign = "x", np.sign(dx)
        else:
            raise Unsupported("schräge Streckenlast")
        for mm, sa, sb, eid in elements:
            if mm.idx != m.idx or sa < num(ll.sa) - TOL or sb > num(ll.sb) + TOL:
                continue
            q1 = num(ll.factor * ll.q_at(sp.Float(sa)))
            q2 = num(ll.factor * ll.q_at(sp.Float(sb)))
            ss.q_load([SIGN_Q_LOAD * sign * q1, SIGN_Q_LOAD * sign * q2], eid, direction=direction)
    return ss, elements


def compare(st: Structure, result: Result) -> list[str]:
    """Liste der Abweichungen (leer = alles stimmt)."""
    ss, elements = build(st, result)
    ss.solve()
    problems = []
    for m, sa, sb, eid in elements:
        mr = result.members[m.idx]
        mid = 0.5 * (sa + sb)
        seg = next(g for g in mr.segments if num(g.sa) - TOL <= mid <= num(g.sb) + TOL)
        res = ss.get_element_results(eid, verbose=True)
        ts = np.linspace(sa, sb, MESH)
        # anaStruct dreht Elemente mit dx < 0 um (Winkel immer in [-90°, 90°]): Ergebnis läuft
        # dann rückwärts, die Faser liegt relativ zum Element auf der anderen Seite.
        # M kehrt sich dadurch um, bei Q heben sich x1- und Faserumkehr auf.
        swapped = num(m.e1[0]) < -TOL
        m_sign = -1 if swapped else 1
        for qty, key, factor in (
            ("N1", "N", SIGN_N),
            ("Q3", "Q", SIGN_Q * m.fiber),
            ("M2", "M", SIGN_M * m.fiber * m_sign),
        ):
            f = sp.lambdify(S, seg.f(qty).subs(numeric_subs(seg.f(qty))))
            ours = np.array([float(f(t)) for t in ts])
            theirs = np.asarray(res[key], dtype=float) / factor
            if swapped:
                theirs = theirs[::-1]
            if not np.allclose(ours, theirs, atol=1e-5, rtol=1e-5):
                problems.append(
                    f"{qty} Stab {m.n0}-{m.n1} [{sa:.3g},{sb:.3g}]: ours {ours[[0, -1]]} vs anaStruct {theirs[[0, -1]]}"
                )
    return problems
