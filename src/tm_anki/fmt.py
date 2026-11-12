"""Exakte Werte als LaTeX (matplotlib-mathtext- und MathJax-tauglich).

Ein Wert wird als ``c * Einheitsmonom`` zerlegt (z. B. 9/32 * q a^2) und als
``\\frac{9 q a^{2}}{32}`` gesetzt: Lastsymbol vor Längensymbol, wie im Lehrbuch.
"""

from __future__ import annotations

import re

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


def _radical_base(expr: sp.Expr) -> sp.Expr | None:
    """Einzige symbolische Wurzelbasis S (Potenzen S^(k/2)), sonst None."""
    bases = {p.base for p in expr.atoms(sp.Pow)
             if p.exp.is_Rational and p.exp.q == 2 and p.base.free_symbols}
    return bases.pop() if len(bases) == 1 else None


def radical_parts(expr) -> tuple[sp.Expr, sp.Expr, sp.Expr, sp.Expr] | None:
    """Zerlegt expr = (a + b*sqrt(S)) / d mit Polynomen a, b, d (gemeinsame Faktoren gekürzt).

    Funktioniert für Ausdrücke mit genau einer symbolischen Wurzelbasis S, z. B. das Feldmoment
    der allgemeinen Trapezlast. Gibt None zurück, wenn das nicht passt.
    """
    expr = sp.sympify(expr)
    inner = _radical_base(expr)
    if inner is None:
        return None
    W = sp.Dummy("W", positive=True)
    e = expr.replace(lambda x: x.is_Pow and x.base == inner and x.exp.is_Rational and x.exp.q == 2,
                     lambda x: W ** (2 * x.exp))
    n, d = sp.fraction(sp.together(e))

    def red(p):  # modulo W^2 = S
        return sp.Poly(sp.expand(p), W).rem(sp.Poly(W**2 - inner, W)).as_expr()

    n, d = red(n), red(d)
    if d.has(W):  # Nenner rational machen
        d0, d1 = d.coeff(W, 0), d.coeff(W, 1)
        n = red(sp.expand(n * (d0 - d1 * W)))
        d = sp.expand(d0**2 - d1**2 * inner)
    a, b = sp.expand(n.coeff(W, 0)), sp.expand(n.coeff(W, 1))
    g = sp.gcd(sp.gcd(a, b), d) if a != 0 and b != 0 else sp.gcd(a if a != 0 else b, d)
    a, b, d = sp.cancel(a / g), sp.cancel(b / g), sp.cancel(d / g)
    return sp.factor(a), sp.factor(b), sp.factor(d), inner


def simplify_radicals(expr) -> sp.Expr:
    """Kompakte Form (a + b*sqrt(S))/d, falls möglich; sonst sympy.simplify."""
    parts = radical_parts(expr)
    if parts is None:
        return sp.simplify(expr)
    a, b, d, inner = parts
    return (a + b * sp.sqrt(inner)) / d


def _latex_add_pos_first(expr: sp.Expr) -> str:
    """Summe mit positiven Termen zuerst (q_2 - q_1 statt -q_1 + q_2)."""
    terms = sp.Add.make_args(sp.expand(expr)) if isinstance(expr, sp.Add) else [expr]
    terms = sorted(terms, key=lambda t: sy.num(t) < 0)
    tex = " + ".join(sp.latex(t) for t in terms)
    return tex.replace("+ -", "- ")


def _latex_radical(v: sp.Expr) -> str | None:
    parts = radical_parts(v)
    if parts is None:
        return None
    a, b, d, inner = parts
    # gemeinsamen Längenfaktor ausklammern
    lens = sp.S.One
    for sym in sy.LENGTH_SYMBOLS:
        degs = [sp.Poly(t, sym).monoms()[-1][0] for t in (sp.expand(a), sp.expand(b)) if t != 0]
        k = min(degs) if degs else 0
        lens *= sym**k
    a, b = sp.factor(sp.cancel(a / lens)), sp.factor(sp.cancel(b / lens))
    # Nennerfaktoren positiv orientieren (z. B. q_2 - q_1)
    sign = 1
    coeff, factors = sp.factor_list(d)
    if coeff < 0:
        sign, coeff = -sign, -coeff
    den_items = [] if coeff == 1 else [sp.latex(coeff)]
    for f, e in factors:
        if sy.num(f) < 0:
            f = sp.expand(-f)
            if e % 2:
                sign = -sign
        tex = _latex_add_pos_first(f) if isinstance(f, sp.Add) else sp.latex(f)
        tex = f"\\left({tex}\\right)" if isinstance(f, sp.Add) else tex
        den_items.append(tex if e == 1 else f"{tex}^{{{e}}}")
    terms = [sign * b * sp.sqrt(inner), sign * a]  # Wurzelterm zuerst, positive Terme vorn
    terms = sorted((t for t in terms if t != 0), key=lambda t: sy.num(t) < 0)
    num_tex = " + ".join(sp.latex(t) for t in terms).replace("+ -", "- ")
    len_tex = "" if lens == 1 else sp.latex(lens)
    if len(terms) > 1 and len_tex:
        num_tex = f"\\left({num_tex}\\right)\\,{len_tex}"
    elif len_tex:
        num_tex = f"{num_tex}\\,{len_tex}"
    den = "".join(den_items)
    return f"\\frac{{{num_tex}}}{{{den}}}" if den else num_tex


def latex_value(value) -> str:
    """LaTeX ohne umschließende ``$``."""
    v = sp.sympify(value)
    if v.free_symbols - set(sy.LOAD_SYMBOLS) - set(sy.LENGTH_SYMBOLS) - {sy.S}:
        return sp.latex(v)
    if _radical_base(v) is not None:  # symbolische Wurzel, z. B. Feldmoment der allgemeinen Trapezlast
        tex = _latex_radical(v)
        if tex is not None:
            return tex
    v = sp.radsimp(sp.simplify(v))
    if v == 0:
        return "0"
    syms = sorted(v.free_symbols, key=_order_key)
    c = sp.radsimp(sp.nsimplify(v.subs({s: 1 for s in syms})))
    if c == 0:
        return _latex_general(v)
    unit = sp.simplify(v / c)
    powers = unit.as_powers_dict()
    monomial = all(k in syms and sp.sympify(e).is_integer for k, e in powers.items() if k != 1)
    if not monomial or sp.simplify(unit - sp.Mul(*[k**e for k, e in powers.items()])) != 0:
        return _latex_general(v)

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
    num = _join(num_parts) if num_parts else "1"
    if den_parts:
        return f"{sign}\\frac{{{num}}}{{{_join(den_parts)}}}"
    return f"{sign}{num}"


_UPPER_SYMBOL = re.compile(r"[A-Z]")


def _join(parts: list[str]) -> str:
    """Faktoren ohne Abstand zusammenziehen (2qa statt 2 q a). Nach einem Großbuchstaben wie F
    kommt ein schmaler Abstand, sonst ragt das kursive F in den nächsten Buchstaben (F\\,l statt Fl)."""
    out = ""
    for i, p in enumerate(parts):
        if i and _UPPER_SYMBOL.fullmatch(parts[i - 1]):
            out += "\\,"
        out += p
    return out


def _latex_general(v: sp.Expr) -> str:
    """Mehrere Lastsymbole, z. B. l*(2*q_1 + q_2)/6 -> \\frac{(2q_1 + q_2)\\,l}{6}."""
    v = sp.factor(v)
    coeff, rest = v.as_coeff_Mul()
    negative = coeff < 0
    cn, cd = sp.fraction(sp.Abs(coeff))
    num_f, den_f = sp.fraction(rest)
    length_set = set(sy.LENGTH_SYMBOLS)

    def side(expr, number) -> tuple[str, bool]:
        """LaTeX einer Seite des Bruchs; zweiter Wert: Vorzeichen wurde umgedreht."""
        flipped = False
        loads, lengths = [], []
        for f in sp.Mul.make_args(expr):
            if f == 1:
                continue
            (lengths if f.free_symbols and f.free_symbols <= length_set else loads).append(f)
        items = [] if number == 1 else [sp.latex(number)]
        multi = len(loads) + len(lengths) + len(items) > 1
        for f in loads:
            base, e = (f.base, f.exp) if f.is_Pow and isinstance(f.base, sp.Add) else (f, 1)
            if isinstance(base, sp.Add):
                if sy.num(base) < 0:  # Summe positiv orientieren: 2qa - F statt F - 2qa
                    base = sp.expand(-base)
                    flipped ^= bool(e % 2)
                tex = _latex_sum(base)
                if e != 1:
                    items.append(f"\\left({tex}\\right)^{{{sp.latex(e)}}}")
                else:
                    items.append(f"\\left({tex}\\right)" if multi else tex)
            else:
                items.append(sp.latex(f))
        lens = sorted(lengths, key=lambda f: _order_key(next(iter(f.free_symbols))))
        tex = "".join(items)
        if lens:
            len_tex = "".join(sp.latex(f) for f in lens)
            tex = f"{tex}\\,{len_tex}" if tex else len_tex
        return tex, flipped

    num, f1 = side(num_f, cn)
    den, f2 = side(den_f, cd)
    sign = "-" if negative ^ f1 ^ f2 else ""
    num = num or "1"
    return f"{sign}\\frac{{{num}}}{{{den}}}" if den else f"{sign}{num}"


def _latex_sum(expr: sp.Expr) -> str:
    """Summe mit positiven Termen zuerst, jeder Term in Lehrbuch-Reihenfolge (2qa - F)."""
    def key(t):
        syms = sorted(t.free_symbols, key=_order_key)
        return (sy.num(t) < 0, _order_key(syms[0]) if syms else (-1, 0, ""))

    terms = sorted(sp.Add.make_args(sp.expand(expr)), key=key)
    out = ""
    for i, t in enumerate(terms):
        neg = sy.num(t) < 0
        body = latex_value(-t if neg else t)
        out += (" - " if neg else (" + " if i else "")) + body
    return out.strip()


#: Ausdrücke bis zu dieser Größe (sympy.count_ops) gelten als einfach genug für die Zeichnung
SIMPLE_OPS = 14


#: Bemaßungen im Verlauf müssen noch kürzer sein (sonst steht dort x_0 und der Ausdruck im Text)
DIM_OPS = 8


def is_simple(value, max_ops: int = SIMPLE_OPS) -> bool:
    v = sp.sympify(value)
    if _radical_base(v) is not None:
        v = simplify_radicals(v)
    else:
        v = sp.factor(v)
    return sp.count_ops(v) <= max_ops


def complex_extrema(result, kps) -> list[tuple]:
    """Extrema, deren Wert oder Lage zu lang fürs Bild ist: [(KeyPoint, Abstand, Name der Lage)].
    Die Lage heißt im Bild x_0 (x_0', x_0'' ...) und wird im Text ausgeschrieben."""
    from .keypoints import extremum_offset  # zyklischen Import vermeiden

    out = []
    for kp in kps:
        if kp.kind != "extrem":
            continue
        dist = extremum_offset(result, kp)
        if is_simple(kp.value) and is_simple(dist, DIM_OPS):
            continue
        name = "x_0" + "'" * len(out) if not is_simple(dist, DIM_OPS) else None
        out.append((kp, dist, name))
    return out


def math(value) -> str:
    """Wert in ``$...$`` für matplotlib."""
    return f"${latex_value(value)}$"
