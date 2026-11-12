"""Katalog-Sprache: kompakte Beschreibung von Systemen.

Beispiel::

    balken("EF05", "Einfeldträger, Streckenlast links", L=2*a,
           lager={0: Fest(), 2*a: Los()}, lasten=[Strecke(0, a, q)])

Zeichenkoordinaten im Katalog: (x, y) mit y nach oben.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sympy as sp

from .fmt import latex_value
from .model import (
    Chain,
    LineLoad,
    Location,
    Member,
    ModelError,
    Node,
    PointForce,
    PointMoment,
    Structure,
    Support,
    SystemDef,
)
from .symbols import F, M0, a, l, laenge, last, num, q, q0, q1, q2  # noqa: F401  (Re-Export)

TOL = 1e-9

#: alle bisher definierten Systeme (für variante())
REGISTRY: dict[str, SystemDef] = {}


# --------------------------------------------------------------------------- Lager


@dataclass(frozen=True)
class Fest:
    """Festlager: Reaktionen horizontal und vertikal."""

    boden: str | None = None


@dataclass(frozen=True)
class Los:
    """Loslager: eine Reaktion unter ``winkel`` (Grad, Zeichenkoordinaten; 90 = senkrecht)."""

    winkel: float = 90
    boden: str | None = None


@dataclass(frozen=True)
class Einspannung:
    """Feste Einspannung: Reaktionen H, V und Moment."""

    boden: str | None = None


# --------------------------------------------------------------------------- Lasten


@dataclass(frozen=True)
class Kraft:
    """Einzelkraft. ``richtung``: "unten" | "oben" | "links" | "rechts" | Winkel in Grad (CCW ab +x)."""

    pos: Any
    P: Any
    richtung: Any = "unten"
    label: str | None = None


@dataclass(frozen=True)
class Moment:
    """Einzelmoment. ``dreh``: "links" (gegen Uhrzeigersinn) | "rechts" (im Uhrzeigersinn)."""

    pos: Any
    M: Any
    dreh: str = "links"
    label: str | None = None


@dataclass(frozen=True)
class Strecke:
    """Linear veränderliche Streckenlast von ``von`` bis ``bis``.

    ``bezug="laenge"``: Intensität je Stablänge, ``"projektion"``: je Projektion senkrecht
    zur Wirkrichtung (z. B. Schnee auf schrägem Dach: je Grundrisslänge).
    """

    von: Any
    bis: Any
    q_von: Any
    q_bis: Any = None
    richtung: Any = "unten"
    bezug: str = "laenge"
    label: str | None = None
    label_bis: str | None = None


@dataclass(frozen=True)
class Stab:
    """Stabzug durch die angegebenen Knoten; Faser rechts/links in Laufrichtung."""

    knoten: tuple[str, ...]
    faser: str = "rechts"

    def __init__(self, *knoten: str, faser: str = "rechts"):
        object.__setattr__(self, "knoten", tuple(knoten))
        object.__setattr__(self, "faser", faser)


# --------------------------------------------------------------------------- Hilfen


def _eq(x, y) -> bool:
    return abs(num(x) - num(y)) < TOL


def _direction(richtung) -> tuple[tuple[sp.Expr, sp.Expr], float]:
    """Einheitsvektor (X, Z) und Winkel in Zeichenkoordinaten."""
    named = {"rechts": 0, "oben": 90, "links": 180, "unten": -90}
    if isinstance(richtung, str):
        if richtung not in named:
            raise ModelError(f"Unbekannte Richtung {richtung!r}")
        deg = named[richtung]
    else:
        deg = richtung
    rad = sp.pi * sp.nsimplify(deg) / 180
    return (sp.cos(rad), -sp.sin(rad)), float(deg)


_FIBER = {"rechts": 1, "links": -1}


class _Builder:
    """Gemeinsamer Aufbau für balken() und rahmen()."""

    def __init__(self, nodes: dict[str, Node], chains: list[tuple[list[str], int]]):
        self.nodes = nodes
        self.members: list[Member] = []
        self.chains: list[Chain] = []
        seen: set[frozenset[str]] = set()
        for ci, (names, fiber) in enumerate(chains):
            if len(names) < 2:
                raise ModelError("Ein Stabzug braucht mindestens zwei Knoten")
            chain = Chain(ci, list(names), fiber)
            s = sp.S.Zero
            chain.node_s[names[0]] = s
            for n0, n1 in zip(names[:-1], names[1:]):
                for n in (n0, n1):
                    if n not in nodes:
                        raise ModelError(f"Unbekannter Knoten {n!r}")
                key = frozenset((n0, n1))
                if key in seen:
                    raise ModelError(f"Stab {n0}-{n1} doppelt definiert")
                seen.add(key)
                p0, p1 = nodes[n0], nodes[n1]
                dx, dz = sp.simplify(p1.x - p0.x), sp.simplify(p1.z - p0.z)
                length = sp.sqrt(sp.simplify(dx**2 + dz**2))
                length = sp.simplify(length)
                if num(length) < TOL:
                    raise ModelError(f"Stab {n0}-{n1} hat Länge 0")
                e1 = (sp.simplify(dx / length), sp.simplify(dz / length))
                e3 = (sp.simplify(-fiber * e1[1]), sp.simplify(fiber * e1[0]))
                m = Member(len(self.members), n0, n1, ci, s, fiber, length, e1, e3, (p0.x, p0.z))
                self.members.append(m)
                chain.members.append(m.idx)
                s = sp.simplify(s + length)
                chain.node_s[n1] = s
            self.chains.append(chain)
        self.point_forces: list[PointForce] = []
        self.point_moments: list[PointMoment] = []
        self.line_loads: list[LineLoad] = []
        self._group = 0

    # ---- Positionen -------------------------------------------------------
    def chain_location(self, ci: int, s) -> Location:
        chain = self.chains[ci]
        for name, sn in chain.node_s.items():
            if _eq(s, sn):
                return Location(node=name)
        for mi in chain.members:
            m = self.members[mi]
            if num(m.s0) - TOL < num(s) < num(m.s0 + m.length) + TOL:
                return Location(member=mi, s=sp.simplify(s - m.s0))
        raise ModelError(f"Position {s} liegt nicht auf Stabzug {ci}")

    # ---- Lasten -----------------------------------------------------------
    def add_force(self, loc: Location, spec: Kraft):
        (dx, dz), deg = _direction(spec.richtung)
        P = sp.sympify(spec.P)
        label = spec.label or latex_value(P)
        self.point_forces.append(PointForce(loc, P * dx, P * dz, P, label, deg))

    def add_moment(self, loc: Location, spec: Moment):
        M = sp.sympify(spec.M)
        if spec.dreh not in ("links", "rechts"):
            raise ModelError("Moment: dreh muss 'links' oder 'rechts' sein")
        m = M if spec.dreh == "links" else -M
        label = spec.label or latex_value(M)
        self.point_moments.append(PointMoment(loc, m, M, label))

    def add_line(self, ci: int, s_von, s_bis, spec: Strecke):
        qa = sp.sympify(spec.q_von)
        qb = sp.sympify(spec.q_von if spec.q_bis is None else spec.q_bis)
        s_von, s_bis = sp.sympify(s_von), sp.sympify(s_bis)
        label_a = spec.label or latex_value(qa)
        label_b = spec.label_bis or (spec.label if spec.q_bis is None else None) or latex_value(qb)
        if num(s_von) > num(s_bis):
            s_von, s_bis, qa, qb = s_bis, s_von, qb, qa
            label_a, label_b = label_b, label_a
        if _eq(s_von, s_bis):
            raise ModelError("Streckenlast der Länge 0")
        if spec.bezug not in ("laenge", "projektion"):
            raise ModelError("Strecke: bezug muss 'laenge' oder 'projektion' sein")
        d, _ = _direction(spec.richtung)
        span = s_bis - s_von

        def q_chain(s):
            return sp.simplify(qa + (qb - qa) * (s - s_von) / span)

        # Beschriftungsanker (Kettenkoordinate)
        if sp.simplify(qa - qb) == 0:
            anchors = [(label_a, sp.simplify((s_von + s_bis) / 2))]
        else:
            anchors = []
            if not _eq(qa, 0):
                anchors.append((label_a, s_von))
            if not _eq(qb, 0):
                anchors.append((label_b, s_bis))

        group = self._group
        self._group += 1
        chain = self.chains[ci]
        pieces: list[tuple[LineLoad, sp.Expr, sp.Expr]] = []
        for mi in chain.members:
            m = self.members[mi]
            m_lo, m_hi = m.s0, sp.simplify(m.s0 + m.length)
            if num(s_bis) <= num(m_lo) + TOL or num(s_von) >= num(m_hi) - TOL:
                continue
            c_lo = s_von if num(s_von) > num(m_lo) else m_lo
            c_hi = s_bis if num(s_bis) < num(m_hi) else m_hi
            factor = sp.S.One
            if spec.bezug == "projektion":
                factor = sp.simplify(sp.Abs(m.e1[0] * d[1] - m.e1[1] * d[0]))
            piece = LineLoad(
                member=mi,
                sa=sp.simplify(c_lo - m.s0),
                sb=sp.simplify(c_hi - m.s0),
                qa=q_chain(c_lo),
                qb=q_chain(c_hi),
                d=d,
                factor=factor,
                bezug=spec.bezug,
                group=group,
            )
            pieces.append((piece, c_lo, c_hi))
        if not pieces:
            raise ModelError("Streckenlast liegt auf keinem Stab")
        for text, s_anchor in anchors:  # jeder Anker genau einmal
            for piece, c_lo, c_hi in pieces:
                if num(c_lo) - TOL <= num(s_anchor) <= num(c_hi) + TOL:
                    s0 = self.members[piece.member].s0
                    piece.labels.append((text, sp.simplify(s_anchor - s0)))
                    break
        self.line_loads.extend(p for p, _, _ in pieces)

    # ---- Abschluss --------------------------------------------------------
    def structure(self, supports, hinges, hinge_labels) -> Structure:
        return Structure(
            nodes=self.nodes,
            members=self.members,
            chains=self.chains,
            supports=supports,
            hinges=list(hinges),
            hinge_labels=hinge_labels,
            point_forces=self.point_forces,
            point_moments=self.point_moments,
            line_loads=self.line_loads,
        )


def _make_support(node: str, label: str, spec) -> Support:
    if isinstance(spec, type):
        spec = spec()
    if isinstance(spec, Fest):
        return Support(
            node, "fest", label, [(sp.S.One, sp.S.Zero), (sp.S.Zero, -sp.S.One)],
            [f"{label}_H", f"{label}_V"], False, spec.boden,
        )
    if isinstance(spec, Los):
        (dx, dz), deg = _direction(spec.winkel)
        return Support(node, "los", label, [(dx, dz)], [label], False, spec.boden, deg)
    if isinstance(spec, Einspannung):
        return Support(
            node, "einspannung", label, [(sp.S.One, sp.S.Zero), (sp.S.Zero, -sp.S.One)],
            [f"{label}_H", f"{label}_V", f"M_{label}"], True, spec.boden,
        )
    raise ModelError(f"Unbekannter Lagertyp {spec!r}")


def _register(sysdef: SystemDef) -> SystemDef:
    REGISTRY[sysdef.id] = sysdef
    return sysdef


DARSTELLUNGEN = ("auto", "im_system", "separat")


def _check_darstellung(darstellung: str | None):
    if darstellung is not None and darstellung not in DARSTELLUNGEN:
        raise ModelError(f"darstellung muss eine von {DARSTELLUNGEN} sein, nicht {darstellung!r}")


# --------------------------------------------------------------------------- balken


def balken(
    id: str,
    titel: str,
    L,
    lager: dict,
    lasten=(),
    gelenke=(),
    faser: str = "unten",
    x1: str = "rechts",
    groessen=None,
    gegeben: str | None = None,
    kategorie: str | None = None,
    darstellung: str | None = None,
    hinweis: str | None = None,
) -> SystemDef:
    """Gerader, horizontaler Balken der Länge ``L``; Positionen von links gemessen."""
    args = dict(id=id, titel=titel, L=L, lager=lager, lasten=lasten, gelenke=gelenke, faser=faser,
                x1=x1, groessen=groessen, gegeben=gegeben, kategorie=kategorie, darstellung=darstellung,
                hinweis=hinweis)
    _check_darstellung(darstellung)
    L = sp.sympify(L)
    if faser not in ("unten", "oben") or x1 not in ("rechts", "links"):
        raise ModelError("balken: faser in {unten, oben}, x1 in {rechts, links}")

    positions: list[sp.Expr] = []
    for p in [0, L, *lager.keys(), *gelenke]:
        p = sp.sympify(p)
        if num(p) < -TOL or num(p) > num(L) + TOL:
            raise ModelError(f"Position {p} außerhalb des Balkens")
        if not any(_eq(p, x) for x in positions):
            positions.append(p)
    positions.sort(key=num)
    names = [f"K{i}" for i in range(len(positions))]
    nodes = {n: Node(n, x, sp.S.Zero) for n, x in zip(names, positions)}

    def node_at(x) -> str:
        for n, px in zip(names, positions):
            if _eq(px, x):
                return n
        raise ModelError(f"Kein Knoten bei {x}")

    walk_right = x1 == "rechts"
    order = names if walk_right else list(reversed(names))
    fiber = 1 if (faser == "unten") == walk_right else -1
    b = _Builder(nodes, [(order, fiber)])

    def s_of(x):
        x = sp.sympify(x)
        return x if walk_right else sp.simplify(L - x)

    supports = []
    for i, (x, spec) in enumerate(sorted(lager.items(), key=lambda kv: num(kv[0]))):
        supports.append(_make_support(node_at(x), "ABCDEFGH"[i], spec))
    hinge_nodes = [node_at(x) for x in gelenke]
    hinge_labels = {n: ("G" if len(hinge_nodes) == 1 else f"G_{i + 1}") for i, n in enumerate(hinge_nodes)}

    for spec in lasten:
        if isinstance(spec, Kraft):
            b.add_force(b.chain_location(0, s_of(spec.pos)), spec)
        elif isinstance(spec, Moment):
            b.add_moment(b.chain_location(0, s_of(spec.pos)), spec)
        elif isinstance(spec, Strecke):
            b.add_line(0, s_of(spec.von), s_of(spec.bis), spec)
        else:
            raise ModelError(f"Unbekannte Last {spec!r}")

    return _register(SystemDef(
        id=id, titel=titel, kategorie=kategorie or "", structure=b.structure(supports, hinge_nodes, hinge_labels),
        groessen=tuple(groessen) if groessen else None, gegeben=gegeben, darstellung=darstellung, hinweis=hinweis, builder=balken,
        args=args,
    ))


# --------------------------------------------------------------------------- rahmen


def rahmen(
    id: str,
    titel: str,
    knoten: dict[str, tuple],
    staebe: list[Stab],
    lager: dict,
    lasten=(),
    gelenke=(),
    groessen=None,
    gegeben: str | None = None,
    kategorie: str | None = None,
    darstellung: str | None = None,
    hinweis: str | None = None,
) -> SystemDef:
    """Allgemeines ebenes Stabwerk aus Stabzügen.

    Lastpositionen: Knotenname oder ``(von, nach, abstand)`` entlang des Stabzugs.
    """
    args = dict(id=id, titel=titel, knoten=knoten, staebe=staebe, lager=lager, lasten=lasten,
                gelenke=gelenke, groessen=groessen, gegeben=gegeben, kategorie=kategorie,
                darstellung=darstellung, hinweis=hinweis)
    _check_darstellung(darstellung)
    nodes = {n: Node(n, sp.sympify(x), -sp.sympify(y)) for n, (x, y) in knoten.items()}
    chains = []
    for st in staebe:
        if st.faser not in _FIBER:
            raise ModelError("Stab: faser muss 'rechts' oder 'links' sein")
        chains.append((list(st.knoten), _FIBER[st.faser]))
    b = _Builder(nodes, chains)

    def chain_with(*names: str) -> int:
        for c in b.chains:
            if all(n in c.node_s for n in names):
                return c.idx
        raise ModelError(f"Kein Stabzug enthält {names}")

    def chain_pos(pos) -> tuple[int, sp.Expr]:
        if isinstance(pos, str):
            ci = chain_with(pos)
            return ci, b.chains[ci].node_s[pos]
        n_from, n_to, dist = pos
        ci = chain_with(n_from, n_to)
        c = b.chains[ci]
        sign = 1 if num(c.node_s[n_to]) > num(c.node_s[n_from]) else -1
        return ci, sp.simplify(c.node_s[n_from] + sign * sp.sympify(dist))

    def location(pos) -> Location:
        if isinstance(pos, str):
            if pos not in nodes:
                raise ModelError(f"Unbekannter Knoten {pos!r}")
            return Location(node=pos)
        ci, s = chain_pos(pos)
        return b.chain_location(ci, s)

    supports = [_make_support(n, n, spec) for n, spec in lager.items()]
    hinge_labels = {n: n for n in gelenke}

    for spec in lasten:
        if isinstance(spec, Kraft):
            b.add_force(location(spec.pos), spec)
        elif isinstance(spec, Moment):
            b.add_moment(location(spec.pos), spec)
        elif isinstance(spec, Strecke):
            ends = [spec.von, spec.bis]
            names = [p if isinstance(p, str) else p[0] for p in ends] + [
                p[1] for p in ends if not isinstance(p, str)
            ]
            ci = chain_with(*dict.fromkeys(names))
            c = b.chains[ci]

            def s_in_chain(p):
                if isinstance(p, str):
                    return c.node_s[p]
                n_from, n_to, dist = p
                sign = 1 if num(c.node_s[n_to]) > num(c.node_s[n_from]) else -1
                return sp.simplify(c.node_s[n_from] + sign * sp.sympify(dist))

            b.add_line(ci, s_in_chain(spec.von), s_in_chain(spec.bis), spec)
        else:
            raise ModelError(f"Unbekannte Last {spec!r}")

    return _register(SystemDef(
        id=id, titel=titel, kategorie=kategorie or "", structure=b.structure(supports, list(gelenke), hinge_labels),
        groessen=tuple(groessen) if groessen else None, gegeben=gegeben, darstellung=darstellung, hinweis=hinweis, builder=rahmen,
        args=args,
    ))


# --------------------------------------------------------------------------- variante

def variante(basis: str | SystemDef, id: str, titel: str | None = None, **aenderungen) -> SystemDef:
    """Kopie eines Systems mit geänderten Parametern, z. B. ``faser="oben"``.

    Der Titel bleibt standardmäßig der des Basissystems: Die Änderung (Faserlage, x1-Richtung) ist in der
    Zeichnung zu sehen und soll beim Lernen erkannt, nicht im Titel verraten werden.
    """
    base = REGISTRY[basis] if isinstance(basis, str) else basis
    if base.builder is None:
        raise ModelError(f"{base.id} lässt sich nicht variieren")
    args = {**base.args, **aenderungen, "id": id, "titel": titel or base.titel}
    if not args.get("kategorie"):
        args["kategorie"] = base.kategorie
    return base.builder(**args)
