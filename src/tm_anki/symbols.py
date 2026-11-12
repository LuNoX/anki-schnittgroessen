"""Symbole für Längen und Lasten.

Neue Symbole lassen sich mit :func:`laenge` bzw. :func:`last` anlegen, damit der
Formatter weiß, ob es sich um eine Länge oder eine Last handelt.
"""

from __future__ import annotations

import sympy as sp

LENGTH_SYMBOLS: list[sp.Symbol] = []
LOAD_SYMBOLS: list[sp.Symbol] = []

#: lokale Stabkoordinate (Laufvariable in den Schnittgrößen-Polynomen)
S = sp.Symbol("s", real=True)


def laenge(name: str) -> sp.Symbol:
    """Neues Längensymbol (positiv)."""
    sym = sp.Symbol(name, positive=True)
    if sym not in LENGTH_SYMBOLS:
        LENGTH_SYMBOLS.append(sym)
    return sym


def last(name: str) -> sp.Symbol:
    """Neues Lastsymbol (positiv)."""
    sym = sp.Symbol(name, positive=True)
    if sym not in LOAD_SYMBOLS:
        LOAD_SYMBOLS.append(sym)
    return sym


a = laenge("a")
l = laenge("l")

F = last("F")
q = last("q")
q0 = last("q_0")
M0 = last("M_0")


def numeric_subs(expr) -> dict:
    """Alle Parameter-Symbole (nicht die Laufvariable) auf 1 setzen."""
    expr = sp.sympify(expr)
    return {s: 1 for s in expr.free_symbols if s != S}


def num(expr) -> float:
    """Zahlenwert eines Ausdrucks mit allen Parametern = 1."""
    expr = sp.sympify(expr)
    return float(expr.subs(numeric_subs(expr)))


def is_zero(expr) -> bool:
    expr = sp.sympify(expr)
    if expr == 0:
        return True
    return sp.simplify(expr) == 0
