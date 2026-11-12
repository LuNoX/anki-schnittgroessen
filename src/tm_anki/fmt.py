"""Exakte Werte als LaTeX (matplotlib-mathtext- und MathJax-tauglich).

Ein Wert wird als ``c * Einheitsmonom`` zerlegt (z. B. 9/32 * q a^2) und als
``\\frac{9 q a^{2}}{32}`` gesetzt: Lastsymbol vor Längensymbol, wie im Lehrbuch.
"""

from __future__ import annotations

import sympy as sp

from . import symbols as sy


def _sym_latex(sym: sp.Symbol) -> str:
    return sp.latex(sym)


def _order_key(sym: sp.Symbol) -> tuple[int, int, str]:
    if sym in sy.LOAD_SYMBOLS:
        return (0, sy.LOAD_SYMBOLS.index(sym), sym.name)
    if sym in sy.LENGTH_SYMBOLS:
        return (1, sy.LENGTH_SYMBOLS.index(sym), sym.name)
    return (2, 0, sym.name)


def _power(sym: sp.Symbol, e: int) -> str:
    base = _sym_latex(sym)
    return base if e == 1 else f"{base}^{{{e}}}"


def _wrap(expr: sp.Expr) -> str:
    text = sp.latex(expr)
    if isinstance(expr, sp.Add):
        return f"\\left({text}\\right)"
    return text


def latex_value(value) -> str:
    """LaTeX ohne umschließende ``$``."""
    v = sp.sympify(value)
    if v.free_symbols - set(sy.LOAD_SYMBOLS) - set(sy.LENGTH_SYMBOLS) - {sy.S}:
        return sp.latex(v)
    v = sp.radsimp(sp.simplify(v))
    if v == 0:
        return "0"
    syms = sorted(v.free_symbols, key=_order_key)
    c = sp.radsimp(sp.nsimplify(v.subs({s: 1 for s in syms})))
    if c == 0:
        return sp.latex(v)
    unit = sp.simplify(v / c)
    powers = unit.as_powers_dict()
    monomial = all(k in syms and sp.sympify(e).is_integer for k, e in powers.items() if k != 1)
    if not monomial or sp.simplify(unit - sp.Mul(*[k**e for k, e in powers.items()])) != 0:
        return sp.latex(v)

    sign = "-" if float(c) < 0 else ""
    c = sp.Abs(c)
    cn, cd = sp.fraction(sp.together(sp.radsimp(c)))
    if isinstance(cn, sp.Add):
        # z. B. (7*sqrt(21) - 27)/27: Zahlenfaktor als eigener Bruch vor die Einheit
        unit_tex = latex_value(unit) if unit != 1 else ""
        terms = sorted(cn.as_ordered_terms(), key=lambda t: float(t) < 0)  # positive Terme zuerst
        num_tex = " + ".join(sp.latex(t) for t in terms).replace("+ -", "- ")
        frac = f"\\frac{{{num_tex}}}{{{sp.latex(cd)}}}" if cd != 1 else f"\\left({num_tex}\\right)"
        return f"{sign}{frac}\\,{unit_tex}"
    num_parts: list[str] = []
    den_parts: list[str] = []
    if cn != 1:
        num_parts.append(_wrap(cn))
    if cd != 1:
        den_parts.append(_wrap(cd))
    for sym in sorted((k for k in powers if k != 1), key=_order_key):
        e = int(powers[sym])
        if e > 0:
            num_parts.append(_power(sym, e))
        elif e < 0:
            den_parts.append(_power(sym, -e))
    num = "\\,".join(_join_tight(num_parts)) if num_parts else "1"
    if den_parts:
        den = "\\,".join(_join_tight(den_parts))
        return f"{sign}\\frac{{{num}}}{{{den}}}"
    return f"{sign}{num}"


def _join_tight(parts: list[str]) -> list[str]:
    """Zahl + Symbole ohne Abstand zusammenziehen (2qa statt 2 q a)."""
    if not parts:
        return parts
    return ["".join(parts)]


def math(value) -> str:
    """Wert in ``$...$`` für matplotlib."""
    return f"${latex_value(value)}$"
