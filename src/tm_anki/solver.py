"""Exakter Solver für statisch bestimmte ebene Stabwerke.

1. Starrkörper = Zusammenhangskomponenten der biegesteifen Verbindungen.
2. Jeder Gelenkknoten ist ein Bolzen, der mit jedem angeschlossenen Körper eine
   unbekannte Gelenkkraft (Hx, Hz) austauscht.
3. Gleichgewicht je Körper (ΣX, ΣZ, ΣM) und je Bolzen (ΣX, ΣZ) -> lineares System.
4. Schnittgrößen: Gleichgewicht des Teils auf der Seite des Stabanfangs
   (positives Schnittufer zeigt in +x1).
"""

from __future__ import annotations

import itertools
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import sympy as sp

from .model import LineLoad, Member, ModelError, Structure, Support
from .symbols import S, num

QUANTITIES = ("N1", "Q3", "M2")
TOL = 1e-9
_T = sp.Symbol("t", real=True)


class StaticsError(ModelError):
    """System ist nicht statisch bestimmt (oder verschieblich)."""


@dataclass
class Force:
    """Kraft (fx, fz) im Punkt (x, z) plus freies Moment m (um +Y)."""

    x: sp.Expr
    z: sp.Expr
    fx: sp.Expr
    fz: sp.Expr
    m: sp.Expr = sp.S.Zero


def _resultant(forces: list[Force]) -> tuple[sp.Expr, sp.Expr, sp.Expr]:
    fx = sum((f.fx for f in forces), sp.S.Zero)
    fz = sum((f.fz for f in forces), sp.S.Zero)
    mo = sum((f.z * f.fx - f.x * f.fz + f.m for f in forces), sp.S.Zero)
    return fx, fz, mo


@dataclass
class Segment:
    sa: sp.Expr
    sb: sp.Expr
    N1: sp.Expr
    Q3: sp.Expr
    M2: sp.Expr

    def f(self, qty: str) -> sp.Expr:
        return getattr(self, qty)


@dataclass
class MemberResult:
    member: Member
    segments: list[Segment]

    def value(self, qty: str, s, side: str = "right") -> sp.Expr:
        """Wert bei s; ``side`` wählt an Abschnittsgrenzen den Grenzwert von links/rechts."""
        segs = self.segments
        x = num(s)
        if side == "right":
            cand = [g for g in segs if num(g.sa) - TOL <= x < num(g.sb) - TOL]
            chosen = cand[0] if cand else segs[-1]
        else:
            cand = [g for g in segs if num(g.sa) + TOL < x <= num(g.sb) + TOL]
            chosen = cand[0] if cand else segs[0]
        return sp.simplify(chosen.f(qty).subs(S, s))


@dataclass
class ReactionValue:
    support: Support
    name: str
    direction: tuple[sp.Expr, sp.Expr] | None  # None = Moment
    value: sp.Expr


@dataclass
class Result:
    structure: Structure
    reactions: list[ReactionValue]
    members: list[MemberResult]
    bodies: list[list[int]] = field(default_factory=list)

    def is_zero(self, qty: str) -> bool:
        return all(sp.expand(seg.f(qty)) == 0 for mr in self.members for seg in mr.segments)

    def nonzero_quantities(self) -> tuple[str, ...]:
        return tuple(qq for qq in QUANTITIES if not self.is_zero(qq))


# --------------------------------------------------------------------------- Lasten -> Kräfte


def _member_point(m: Member, s) -> tuple[sp.Expr, sp.Expr]:
    return m.point(s)


def _line_force(ll: LineLoad, m: Member, upper) -> Force:
    """Resultierende der Streckenlast von sa bis ``upper`` (als Kraft im Ursprung + Moment)."""
    w = ll.factor * ll.q_at(_T)
    dx, dz = ll.d
    R = sp.integrate(w, (_T, ll.sa, upper))
    rx = m.r0[0] + _T * m.e1[0]
    rz = m.r0[1] + _T * m.e1[1]
    mo = sp.integrate((rz * dx - rx * dz) * w, (_T, ll.sa, upper))
    return Force(sp.S.Zero, sp.S.Zero, R * dx, R * dz, mo)


class _Loads:
    """Ordnet alle Lasten Stäben bzw. Knoten zu."""

    def __init__(self, st: Structure):
        self.member_points: dict[int, list[tuple[sp.Expr, Force]]] = defaultdict(list)
        self.member_lines: dict[int, list[LineLoad]] = defaultdict(list)
        self.node_forces: dict[str, list[Force]] = defaultdict(list)
        self.node_moment_nodes: set[str] = set()
        for pf in st.point_forces:
            self._add(st, pf.at, pf.fx, pf.fz, sp.S.Zero)
        for pm in st.point_moments:
            self._add(st, pm.at, sp.S.Zero, sp.S.Zero, pm.m)
            if pm.at.node is not None:
                self.node_moment_nodes.add(pm.at.node)
        for ll in st.line_loads:
            self.member_lines[ll.member].append(ll)

    def _add(self, st: Structure, at, fx, fz, m):
        if at.node is not None:
            n = st.nodes[at.node]
            self.node_forces[at.node].append(Force(n.x, n.z, fx, fz, m))
        else:
            mem = st.members[at.member]
            x, z = _member_point(mem, at.s)
            self.member_points[at.member].append((at.s, Force(x, z, fx, fz, m)))

    def member_full(self, m: Member) -> list[Force]:
        out = [f for _, f in self.member_points[m.idx]]
        out += [_line_force(ll, m, ll.sb) for ll in self.member_lines[m.idx]]
        return out


# --------------------------------------------------------------------------- Solver


def solve(st: Structure) -> Result:
    nm = len(st.members)
    hinges = set(st.hinges)
    for h in hinges:
        if h not in st.nodes:
            raise ModelError(f"Gelenk an unbekanntem Knoten {h!r}")

    # --- Starrkörper (Union-Find) -----------------------------------------
    parent = list(range(nm))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for name in st.nodes:
        if name in hinges:
            continue
        ms = st.members_at(name)
        for m in ms[1:]:
            parent[find(m.idx)] = find(ms[0].idx)
    roots = sorted({find(i) for i in range(nm)})
    body_of = {i: roots.index(find(i)) for i in range(nm)}
    bodies = [[i for i in range(nm) if body_of[i] == b] for b in range(len(roots))]

    pins: dict[str, list[int]] = {}
    for h in sorted(hinges):
        attached = [body_of[m.idx] for m in st.members_at(h)]
        if len(set(attached)) < 2:
            raise ModelError(f"Gelenk {h} verbindet weniger als zwei Teilkörper")
        if len(set(attached)) != len(attached):
            raise StaticsError(f"Geschlossener Ring über Gelenk {h}: innerlich statisch unbestimmt")
        pins[h] = sorted(set(attached))

    def body_of_node(name: str) -> int:
        ms = st.members_at(name)
        if not ms:
            raise ModelError(f"Knoten {name} hängt an keinem Stab")
        return body_of[ms[0].idx]

    loads = _Loads(st)
    for n in loads.node_moment_nodes:
        if n in hinges:
            raise ModelError(f"Einzelmoment direkt im Gelenk {n} ist nicht eindeutig zuordenbar")

    # --- Unbekannte --------------------------------------------------------
    unknowns: list[sp.Symbol] = []
    reaction_terms: list[tuple[Support, str, tuple | None, sp.Symbol]] = []
    support_forces: dict[str, list[Force]] = defaultdict(list)
    for sup in st.supports:
        node = st.nodes[sup.node]
        for d, name in zip(sup.directions, sup.component_names):
            r = sp.Symbol(f"__R{len(unknowns)}")
            unknowns.append(r)
            reaction_terms.append((sup, name, d, r))
            support_forces[sup.node].append(Force(node.x, node.z, d[0] * r, d[1] * r))
        if sup.moment:
            if sup.node in hinges:
                raise ModelError("Einspannung an einem Gelenkknoten ist nicht sinnvoll")
            r = sp.Symbol(f"__R{len(unknowns)}")
            unknowns.append(r)
            reaction_terms.append((sup, sup.component_names[-1], None, r))
            support_forces[sup.node].append(Force(node.x, node.z, sp.S.Zero, sp.S.Zero, r))

    hinge_force: dict[tuple[str, int], Force] = {}
    for h, bs in pins.items():
        node = st.nodes[h]
        for b in bs:
            hx = sp.Symbol(f"__H{len(unknowns)}")
            unknowns.append(hx)
            hz = sp.Symbol(f"__H{len(unknowns)}")
            unknowns.append(hz)
            hinge_force[(h, b)] = Force(node.x, node.z, hx, hz)

    # --- Gleichgewicht -----------------------------------------------------
    body_forces: dict[int, list[Force]] = defaultdict(list)
    for mi in range(nm):
        body_forces[body_of[mi]] += loads.member_full(st.members[mi])
    pin_forces: dict[str, list[Force]] = defaultdict(list)
    for name in st.nodes:
        extra = loads.node_forces.get(name, []) + support_forces.get(name, [])
        if not extra:
            continue
        if name in hinges:
            pin_forces[name] += extra
        else:
            body_forces[body_of_node(name)] += extra
    for (h, b), f in hinge_force.items():
        body_forces[b].append(f)
        pin_forces[h].append(Force(f.x, f.z, -f.fx, -f.fz))

    eqs = []
    for b in range(len(bodies)):
        fx, fz, mo = _resultant(body_forces[b])
        eqs += [fx, fz, mo]
    for h in pins:
        fx, fz, _ = _resultant(pin_forces[h])
        eqs += [fx, fz]

    A, rhs = sp.linear_eq_to_matrix([sp.expand(e) for e in eqs], unknowns)
    n_eq, n_unk = A.shape
    A_num = A.subs(dict.fromkeys(A.free_symbols, 1))
    rank = A_num.rank()
    if n_unk != n_eq or rank < n_unk:
        n_reactions = sum(len(s.directions) + int(s.moment) for s in st.supports)
        if n_unk > rank and n_eq == rank:
            kind = "statisch unbestimmt"
        elif n_unk < n_eq or rank < n_eq:
            kind = "verschieblich (kinematisch)" if n_unk <= n_eq else "statisch unbestimmt und verschieblich"
        else:
            kind = "nicht eindeutig lösbar"
        raise StaticsError(
            f"System ist {kind}: {n_reactions} Lagerreaktionen, {len(bodies)} Teilkörper, "
            f"{len(pins)} Gelenk(e) -> {n_unk} Unbekannte, {n_eq} Gleichungen, Rang {rank}"
        )
    sol_vec = A.LUsolve(rhs)
    sol: dict[Any, Any] = {u: sp.simplify(v) for u, v in zip(unknowns, sol_vec)}

    def subs(f: Force) -> Force:
        return Force(f.x, f.z, sp.sympify(f.fx).subs(sol), sp.sympify(f.fz).subs(sol), sp.sympify(f.m).subs(sol))

    reactions = [ReactionValue(sup, name, d, sol[r]) for sup, name, d, r in reaction_terms]

    # --- Schnittgrößen -----------------------------------------------------
    members: list[MemberResult] = []
    for b, mids in enumerate(bodies):
        adj: dict[object, list[tuple[int, object]]] = defaultdict(list)

        def vert(name: str, mi: int):
            return (name, mi) if name in hinges else name

        for mi in mids:
            m = st.members[mi]
            v0, v1 = vert(m.n0, mi), vert(m.n1, mi)
            adj[v0].append((mi, v1))
            adj[v1].append((mi, v0))
        if len(mids) != len(adj) - 1:
            raise StaticsError("Geschlossener Rahmen (Ring) ist innerlich statisch unbestimmt")

        for mi in mids:
            m = st.members[mi]
            v0 = vert(m.n0, mi)
            seen_v = {v0}
            comp_members: list[int] = []
            queue = deque([v0])
            while queue:
                v = queue.popleft()
                for mj, w in adj[v]:
                    if mj == mi or mj in comp_members:
                        continue
                    comp_members.append(mj)
                    if w not in seen_v:
                        seen_v.add(w)
                        queue.append(w)
            base: list[Force] = []
            for mj in comp_members:
                base += loads.member_full(st.members[mj])
            for v in seen_v:
                if isinstance(v, tuple):
                    base.append(hinge_force[(v[0], b)])
                else:
                    base += loads.node_forces.get(v, []) + support_forces.get(v, [])
            base = [subs(f) for f in base]
            members.append(_member_segments(m, base, loads, subs))

    members.sort(key=lambda r: r.member.idx)
    return Result(st, reactions, members, bodies)


def _member_segments(m: Member, base: list[Force], loads: _Loads, subs) -> MemberResult:
    pts = loads.member_points[m.idx]
    lines = loads.member_lines[m.idx]
    bps: list[sp.Expr] = [sp.S.Zero, m.length]
    for s, _ in pts:
        bps.append(s)
    for ll in lines:
        bps += [ll.sa, ll.sb]
    uniq: list[sp.Expr] = []
    for b in sorted(bps, key=num):
        if not uniq or abs(num(b) - num(uniq[-1])) > TOL:
            uniq.append(sp.simplify(b))

    segments = []
    for sa, sb in itertools.pairwise(uniq):
        lo = num(sa)
        forces = list(base)
        forces += [f for s, f in pts if num(s) <= lo + TOL]
        for ll in lines:
            if num(ll.sb) <= lo + TOL:
                forces.append(_line_force(ll, m, ll.sb))
            elif num(ll.sa) <= lo + TOL:
                forces.append(_line_force(ll, m, S))
        forces = [subs(f) for f in forces]
        fx, fz, mo = _resultant(forces)
        cx, cz = m.point(S)
        mc = mo - (cz * fx - cx * fz)
        N1 = -(fx * m.e1[0] + fz * m.e1[1])
        Q3 = -(fx * m.e3[0] + fz * m.e3[1])
        M2 = -m.fiber * mc
        segments.append(Segment(sa, sb, *(sp.expand(sp.simplify(e)) for e in (N1, Q3, M2))))
    return MemberResult(m, segments)
