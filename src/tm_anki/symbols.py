"""Symbole für Längen und Lasten.

Neue Symbole lassen sich mit :func:`laenge` bzw. :func:`last` anlegen, damit der
Formatter weiß, ob es sich um eine Länge oder eine Last handelt.
"""

from __future__ import annotations

import sympy as sp

LENGTH_SYMBOLS: list[sp.Symbol] = []
LOAD_SYMBOLS: list[sp.Symbol] = []

#: Zahlenwert je Symbol fürs Zeichnen und für Fallunterscheidungen (Standard 1).
#: Unabhängige Lasten wie q_1, q_2 brauchen verschiedene Werte, sonst wäre q_2 - q_1 = 0.
ZEICHENWERTE: dict[sp.Symbol, float] = {}

#: lokale Stabkoordinate (Laufvariable in den Schnittgrößen-Polynomen)
S = sp.Symbol("s", real=True)


def laenge(name: str, zeichenwert: float = 1) -> sp.Symbol:
    """Neues Längensymbol (positiv)."""
    sym = sp.Symbol(name, positive=True)
    if sym not in LENGTH_SYMBOLS:
        LENGTH_SYMBOLS.append(sym)
    ZEICHENWERTE[sym] = zeichenwert
    return sym


def last(name: str, zeichenwert: float = 1) -> sp.Symbol:
    """Neues Lastsymbol (positiv). ``zeichenwert`` = Zahlenwert in der Zeichnung."""
    sym = sp.Symbol(name, positive=True)
    if sym not in LOAD_SYMBOLS:
        LOAD_SYMBOLS.append(sym)
    ZEICHENWERTE[sym] = zeichenwert
    return sym


a = laenge("a")
l = laenge("l")

F = last("F", zeichenwert=0.75)  # nicht 1, sonst zeigt eine Zeichnung mit F und q den Sonderfall F = qa
q = last("q")
q0 = last("q_0")
M0 = last("M_0")
q1 = last("q_1", zeichenwert=1)  # allgemeine Trapezlast: gezeichnet mit q_2 = 2 q_1
q2 = last("q_2", zeichenwert=2)


def numeric_subs(expr) -> dict:
    """Alle Parameter-Symbole (nicht die Laufvariable) auf ihren Zeichenwert setzen."""
    expr = sp.sympify(expr)
    return {s: ZEICHENWERTE.get(s, 1) for s in expr.free_symbols if s != S}


def num(expr) -> float:
    """Zahlenwert eines Ausdrucks mit den Zeichenwerten der Parameter."""
    expr = sp.sympify(expr)
    return float(expr.subs(numeric_subs(expr)))


def is_zero(expr) -> bool:
    expr = sp.sympify(expr)
    if expr == 0:
        return True
    return sp.simplify(expr) == 0
