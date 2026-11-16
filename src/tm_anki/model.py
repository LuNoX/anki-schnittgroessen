"""Internes Datenmodell eines ebenen Stabwerks.

Koordinaten: global X nach rechts, Z nach unten, Y = Z x X (aus der Bildebene heraus).
Positive Momente um Y drehen also (im Bild) gegen den Uhrzeigersinn.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import sympy as sp


class ModelError(ValueError):
    """Fehler in der Systemdefinition."""


@dataclass(frozen=True)
class Node:
    name: str
    x: sp.Expr  # global X (rechts)
    z: sp.Expr  # global Z (unten)

    @property
    def pos(self) -> tuple[sp.Expr, sp.Expr]:
        return (self.x, self.z)


@dataclass
class Member:
    """Gerader Stab zwischen zwei Knoten, orientiert in Laufrichtung des Stabzugs."""

    idx: int
    n0: str
    n1: str
    chain: int
    s0: sp.Expr  # Bogenlänge x1 am Stabanfang (entlang des Stabzugs)
    fiber: int  # +1: Faser rechts in Laufrichtung, -1: links
    length: sp.Expr = sp.S.Zero
    e1: tuple[sp.Expr, sp.Expr] = (sp.S.One, sp.S.Zero)  # Einheitsvektor x1 (X, Z)
    e3: tuple[sp.Expr, sp.Expr] = (sp.S.Zero, sp.S.One)  # Einheitsvektor x3 (X, Z)
    r0: tuple[sp.Expr, sp.Expr] = (sp.S.Zero, sp.S.Zero)  # Position des Stabanfangs

    def point(self, s) -> tuple[sp.Expr, sp.Expr]:
        return (self.r0[0] + s * self.e1[0], self.r0[1] + s * self.e1[1])


@dataclass
class Chain:
    """Stabzug: x1 läuft vom ersten zum letzten Knoten, Faser auf einer Seite."""

    idx: int
    nodes: list[str]
    fiber: int
    members: list[int] = field(default_factory=list)
    node_s: dict[str, sp.Expr] = field(default_factory=dict)  # Bogenlänge je Knoten


@dataclass
class Support:
    node: str
    kind: str  # "fest" | "los" | "einspannung"
    label: str  # z. B. "A"
    directions: list[tuple[sp.Expr, sp.Expr]]  # Einheitsvektoren der Reaktionskräfte (X, Z)
    component_names: list[str]
    moment: bool
    ground: str | None = None  # Zeichen-Override: "unten" | "oben" | "links" | "rechts"
    angle_deg: float | None = None  # Loslager: Winkel der Reaktionslinie (Zeichenkoordinaten)


@dataclass
class Location:
    """Lastangriffspunkt: entweder ein Knoten oder eine Stelle auf einem Stab."""

    node: str | None = None
    member: int | None = None
    s: sp.Expr | None = None  # lokale Koordinate auf dem Stab


@dataclass
class PointForce:
    at: Location
    fx: sp.Expr
    fz: sp.Expr
    magnitude: sp.Expr
    label: str
    angle_deg: float  # Wirkrichtung in Zeichenkoordinaten (CCW ab +x, y oben)


@dataclass
class PointMoment:
    at: Location
    m: sp.Expr  # um +Y, also gegen den Uhrzeigersinn positiv
    magnitude: sp.Expr
    label: str


@dataclass
class LineLoad:
    """Linear veränderliche Streckenlast auf einem Stabstück [sa, sb] (lokal)."""

    member: int
    sa: sp.Expr
    sb: sp.Expr
    qa: sp.Expr
    qb: sp.Expr
    d: tuple[sp.Expr, sp.Expr]  # Wirkrichtung (Einheitsvektor X, Z)
    factor: sp.Expr  # 1 (je Stablänge) oder Projektionsfaktor
    bezug: str  # "laenge" | "projektion"
    group: int  # zusammengehörige Teilstücke einer Katalog-Streckenlast
    labels: list[tuple[str, sp.Expr]] = field(default_factory=list)  # (Text, Kettenposition)

    def q_at(self, t):
        if self.sb == self.sa:
            return self.qa
        return self.qa + (self.qb - self.qa) * (t - self.sa) / (self.sb - self.sa)


@dataclass
class Structure:
    nodes: dict[str, Node]
    members: list[Member]
    chains: list[Chain]
    supports: list[Support]
    hinges: list[str]
    hinge_labels: dict[str, str]
    point_forces: list[PointForce]
    point_moments: list[PointMoment]
    line_loads: list[LineLoad]

    def members_at(self, node: str) -> list[Member]:
        return [m for m in self.members if node in (m.n0, m.n1)]

    def support_at(self, node: str) -> Support | None:
        for sup in self.supports:
            if sup.node == node:
                return sup
        return None


@dataclass
class SystemDef:
    id: str
    titel: str
    kategorie: str
    structure: Structure
    groessen: tuple[str, ...] | None = None  # None = automatisch (alle != 0)
    gegeben: str | None = None  # LaTeX, z. B. r"F < 2qa"
    hinweis: str | None = None  # Lösungshinweis auf der Rückseite (HTML/MathJax), z. B. "als Überlagerung ..."
    darstellung: str | None = None  # "auto" | "im_system" | "separat"; None = conventions.DARSTELLUNG
    builder: Callable[..., SystemDef] | None = None
    args: dict[str, Any] = field(default_factory=dict)
