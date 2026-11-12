import pytest
import sympy as sp

from tm_anki.dsl import Einspannung, Fest, Kraft, Los, Moment, Strecke, balken
from tm_anki.solver import StaticsError, solve
from tm_anki.symbols import F, M0, S, a, l, q, q0


def _eq(x, y):
    return sp.simplify(sp.sympify(x) - sp.sympify(y)) == 0


def reaction(res, name):
    return next(r.value for r in res.reactions if r.name == name)


def val(res, qty, s, member=0, side="right"):
    return res.members[member].value(qty, s, side)


def max_moment(res, member=0):
    """Extremum von M2 im Inneren eines Abschnitts (dM/ds = 0)."""
    for seg in res.members[member].segments:
        roots = sp.solve(sp.diff(seg.M2, S), S)
        for r in roots:
            if seg.sa.subs({a: 1, l: 1}) < r.subs({a: 1, l: 1}) < seg.sb.subs({a: 1, l: 1}):
                return r, sp.simplify(seg.M2.subs(S, r))
    raise AssertionError("kein inneres Extremum")


def test_ef01_einzelkraft_mittig():
    res = solve(balken("T01", "", L=l, lager={0: Fest(), l: Los()}, lasten=[Kraft(l / 2, F)]).structure)
    assert _eq(reaction(res, "A_V"), F / 2) and _eq(reaction(res, "B"), F / 2)
    assert _eq(val(res, "M2", l / 2), F * l / 4)
    assert _eq(val(res, "Q3", l / 2, side="left"), F / 2)
    assert _eq(val(res, "Q3", l / 2, side="right"), -F / 2)


def test_ef04_gleichstreckenlast():
    res = solve(balken("T04", "", L=l, lager={0: Fest(), l: Los()}, lasten=[Strecke(0, l, q)]).structure)
    assert _eq(val(res, "Q3", 0), q * l / 2)
    assert _eq(val(res, "Q3", l, side="left"), -q * l / 2)
    x, m = max_moment(res)
    assert _eq(x, l / 2) and _eq(m, q * l**2 / 8)
    assert res.is_zero("N1")


def test_ef05_streckenlast_links():
    res = solve(balken("T05", "", L=2 * a, lager={0: Fest(), 2 * a: Los()}, lasten=[Strecke(0, a, q)]).structure)
    assert _eq(reaction(res, "A_V"), 3 * q * a / 4)
    assert _eq(reaction(res, "B"), q * a / 4)
    x, m = max_moment(res)
    assert _eq(x, 3 * a / 4) and _eq(m, 9 * q * a**2 / 32)


def test_ef07_dreieckslast():
    res = solve(balken("T07", "", L=l, lager={0: Fest(), l: Los()}, lasten=[Strecke(0, l, 0, q0)]).structure)
    assert _eq(reaction(res, "A_V"), q0 * l / 6)
    assert _eq(reaction(res, "B"), q0 * l / 3)
    x, m = max_moment(res)
    assert _eq(x, l / sp.sqrt(3))
    assert _eq(m, q0 * l**2 / (9 * sp.sqrt(3)))


def test_ef11_moment_mittig():
    res = solve(balken("T11", "", L=l, lager={0: Fest(), l: Los()}, lasten=[Moment(l / 2, M0)]).structure)
    # gegen den Uhrzeigersinn (= um +x2): A nach oben, B nach unten, M2 springt um -M0
    assert _eq(reaction(res, "A_V"), M0 / l)
    assert _eq(reaction(res, "B"), -M0 / l)
    assert _eq(val(res, "Q3", l / 4), M0 / l)
    assert _eq(val(res, "M2", l / 2, side="left"), M0 / 2)
    assert _eq(val(res, "M2", l / 2, side="right"), -M0 / 2)


def test_ef13_schraege_kraft_normalkraft():
    res = solve(balken("T13", "", L=l, lager={0: Fest(), l: Los()},
                       lasten=[Kraft(l / 2, F, richtung=-45)]).structure)
    assert _eq(val(res, "N1", l / 4), sp.sqrt(2) * F / 2)  # Zug links der Kraft
    assert _eq(val(res, "N1", 3 * l / 4), 0)


def test_ef15_festlager_rechts():
    res = solve(balken("T15", "", L=2 * a, lager={0: Los(), 2 * a: Fest()},
                       lasten=[Kraft(a, F, richtung="rechts")]).structure)
    assert _eq(val(res, "N1", a / 2), 0)
    assert _eq(val(res, "N1", 3 * a / 2), -F)  # Druck vor dem Festlager


def test_ka01_kragarm_einzelkraft():
    res = solve(balken("T21", "", L=l, lager={0: Einspannung()}, lasten=[Kraft(l, F)]).structure)
    assert _eq(val(res, "M2", 0), -F * l)
    assert _eq(val(res, "Q3", l / 2), F)
    assert _eq(reaction(res, "M_A"), F * l)


def test_ka10_einspannung_rechts():
    res = solve(balken("T30", "", L=l, lager={l: Einspannung()}, lasten=[Kraft(0, F)]).structure)
    assert _eq(val(res, "Q3", l / 2), -F)
    assert _eq(val(res, "M2", l, side="left"), -F * l)


def test_faser_oben_kehrt_moment_um():
    res = solve(balken("T40", "", L=l, lager={0: Fest(), l: Los()}, lasten=[Strecke(0, l, q)],
                       faser="oben").structure)
    assert _eq(val(res, "M2", l / 2), -q * l**2 / 8)
    assert _eq(val(res, "Q3", 0), -q * l / 2)


def test_x1_nach_links():
    res = solve(balken("T41", "", L=3 * a, lager={0: Fest(), 3 * a: Los()}, lasten=[Kraft(a, F)],
                       x1="links").structure)
    # x1 startet rechts (Lager B, B = F/3): Querkraft kehrt sich gegenüber x1 nach rechts um,
    # das Moment (Faser unten) bleibt positiv
    assert _eq(val(res, "Q3", a / 2), F / 3)
    assert _eq(val(res, "Q3", 5 * a / 2), -2 * F / 3)
    assert _eq(val(res, "M2", 2 * a), 2 * F * a / 3)


def test_gerber_gelenk_momentenfrei():
    res = solve(balken("T50", "", L=3 * a, lager={0: Einspannung(), 3 * a: Los()}, gelenke=[a],
                       lasten=[Strecke(0, 3 * a, q)]).structure)
    assert _eq(val(res, "M2", a, member=0, side="left"), 0)
    assert _eq(val(res, "M2", 0, member=1), 0)
    assert _eq(reaction(res, "B"), q * a)
    assert _eq(reaction(res, "M_A"), 3 * q * a**2 / 2)


def test_statisch_unbestimmt_wird_abgelehnt():
    sysdef = balken("T60", "", L=l, lager={0: Einspannung(), l: Los()}, lasten=[Strecke(0, l, q)])
    with pytest.raises(StaticsError, match="statisch unbestimmt"):
        solve(sysdef.structure)


def test_verschieblich_wird_abgelehnt():
    sysdef = balken("T61", "", L=l, lager={0: Los(), l: Los()}, lasten=[Kraft(l / 2, F)])
    with pytest.raises(StaticsError, match="verschieblich"):
        solve(sysdef.structure)
