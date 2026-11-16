import sympy as sp

from tm_anki.dsl import Einspannung, Fest, Kraft, Los, Stab, Strecke, rahmen
from tm_anki.solver import solve
from tm_anki.symbols import F, a, q


def _eq(x, y):
    return sp.simplify(sp.sympify(x) - sp.sympify(y)) == 0


def reaction(res, name):
    return next(r.value for r in res.reactions if r.name == name)


def member(res, n0, n1):
    return next(mr for mr in res.members if (mr.member.n0, mr.member.n1) == (n0, n1))


PORTAL = {"A": (0, 0), "B": (0, 2 * a), "C": (2 * a, 2 * a), "D": (2 * a, 0)}


def test_dreigelenkrahmen_horizontalschub():
    knoten = {"A": (0, 0), "B": (0, 2 * a), "G": (a, 2 * a), "C": (2 * a, 2 * a), "D": (2 * a, 0)}
    res = solve(
        rahmen(
            "R1",
            "",
            knoten,
            [Stab("A", "B", "G", "C", "D")],
            {"A": Fest(), "D": Fest()},
            [Kraft("G", F)],
            gelenke=["G"],
        ).structure
    )
    assert _eq(reaction(res, "A_H"), F / 4)
    assert _eq(reaction(res, "D_H"), -F / 4)
    assert _eq(member(res, "B", "G").value("M2", a, "left"), 0)
    assert _eq(member(res, "A", "B").value("M2", 2 * a, "left"), -F * a / 2)  # Zug außen


def test_portal_ecke_tauscht_n_und_q_und_m_stetig():
    res = solve(
        rahmen(
            "R2", "", PORTAL, [Stab("A", "B", "C", "D")], {"A": Fest(), "D": Los()}, [Kraft("B", F, richtung="rechts")]
        ).structure
    )
    ab, bc = member(res, "A", "B"), member(res, "B", "C")
    # 90°-Ecke: Q3 im Stiel wird zu N1 im Riegel (bis auf die Knotenlast), M2 stetig
    assert _eq(ab.value("M2", 2 * a, "left"), bc.value("M2", 0, "right"))
    assert _eq(ab.value("Q3", a), F)
    assert _eq(ab.value("N1", a), F)
    assert _eq(bc.value("N1", a), 0)
    assert _eq(bc.value("Q3", a), -F)


def test_winkeltraeger():
    knoten = {"A": (0, 0), "B": (0, 2 * a), "C": (a, 2 * a)}
    res = solve(rahmen("R3", "", knoten, [Stab("A", "B", "C")], {"A": Einspannung()}, [Kraft("C", F)]).structure)
    assert _eq(member(res, "A", "B").value("N1", a), -F)
    # Faser rechts = innen; Zug liegt außen -> M2 negativ, an der Ecke stetig
    assert _eq(member(res, "A", "B").value("M2", a), -F * a)
    assert _eq(member(res, "B", "C").value("M2", 0), -F * a)
    assert _eq(member(res, "B", "C").value("Q3", a / 2), F)


def test_schraeger_balken_projektion():
    knoten = {"A": (0, 0), "B": (4 * a, 3 * a)}
    res = solve(
        rahmen(
            "R4", "", knoten, [Stab("A", "B")], {"A": Fest(), "B": Los()}, [Strecke("A", "B", q, bezug="projektion")]
        ).structure
    )
    # Gesamtlast 4qa, je Lager 2qa; Feldmoment wie Einfeldträger mit Stützweite 4a: q(4a)^2/8
    assert _eq(reaction(res, "A_V"), 2 * q * a)
    mr = res.members[0]
    assert _eq(mr.value("M2", 5 * a / 2), 2 * q * a**2)
    assert _eq(mr.value("Q3", 0), 2 * q * a * sp.Rational(4, 5))
    assert _eq(mr.value("N1", 0), -2 * q * a * sp.Rational(3, 5))


def test_kragstiel_auf_einfeldtraeger():
    knoten = {"A": (0, 0), "M": (2 * a, 0), "B": (4 * a, 0), "S": (2 * a, a)}
    res = solve(
        rahmen(
            "R5",
            "",
            knoten,
            [Stab("A", "M", "B", faser="rechts"), Stab("M", "S", faser="rechts")],
            {"A": Fest(), "B": Los()},
            [Kraft("S", F, richtung="rechts")],
        ).structure
    )
    am, mb = member(res, "A", "M"), member(res, "M", "B")
    # Momentensprung F*a im Riegel am Anschluss des Stiels
    jump = mb.value("M2", 0, "right") - am.value("M2", 2 * a, "left")
    assert _eq(sp.Abs(jump), F * a)
    assert _eq(am.value("N1", a), F)  # Festlager links hält H -> Feld A-M auf Zug
    assert _eq(mb.value("N1", a), 0)
