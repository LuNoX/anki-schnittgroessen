"""Katalog, Kennwerte, Rendering und Deck-Export."""

import zipfile

import pytest
import sympy as sp

from tm_anki.checks import check
from tm_anki.deck import make_cards, write_package
from tm_anki.dsl import Fest, Kraft, Los, Strecke, balken
from tm_anki.fmt import latex_value
from tm_anki.katalog import alle_systeme
from tm_anki.keypoints import extremes, keypoints
from tm_anki.solver import solve
from tm_anki.symbols import F, a, l, q, q0

SYSTEME = alle_systeme()


def test_ids_eindeutig_und_kategorien_gesetzt():
    ids = [s.id for s in SYSTEME]
    assert len(ids) == len(set(ids))
    assert all(s.kategorie for s in SYSTEME)


@pytest.mark.parametrize("sysdef", SYSTEME, ids=[s.id for s in SYSTEME])
def test_invarianten(sysdef):
    result = solve(sysdef.structure)
    errors, warnings = check(sysdef, result)
    assert not errors, errors
    assert not warnings, warnings
    assert result.nonzero_quantities(), "mindestens eine Karte pro System"


def test_kennwerte_einfeld_streckenlast_links():
    res = solve(balken("K1", "", L=2 * a, lager={0: Fest(), 2 * a: Los()}, lasten=[Strecke(0, a, q)]).structure)
    pos, neg = extremes(keypoints(res, "M2"))
    assert sp.simplify(pos.value - 9 * q * a**2 / 32) == 0
    assert sp.simplify(pos.x1 - 3 * a / 4) == 0
    assert neg is None


def test_kennwerte_konstanter_bereich_ueber_gelenk_nur_einmal():
    from tm_anki.dsl import Einspannung

    res = solve(balken("K2", "", L=3 * a, lager={0: Einspannung(), 3 * a: Los()}, gelenke=[a],
                       lasten=[Kraft(2 * a, F)]).structure)
    werte = [k.value for k in keypoints(res, "Q3")]
    assert werte.count(F / 2) == 1


def test_allgemeine_trapezlast():
    from tm_anki.symbols import q1, q2

    sysdef = {s.id: s for s in SYSTEME}["EF09"]
    res = solve(sysdef.structure)
    a_v = next(r.value for r in res.reactions if r.name == "A_V")
    assert sp.simplify(a_v - (2 * q1 + q2) * l / 6) == 0
    assert latex_value(a_v) == r"\frac{\left(2q_{1} + q_{2}\right)\,l}{6}"
    pos, _ = extremes(keypoints(res, "M2"))
    assert pos.kind == "extrem"  # liegt bei Q3 = 0, Wert zu unhandlich fürs Bild
    # geschlossene Form: max M2 = (2*sqrt(3)*S^(3/2) - 9 q1 q2 (q1 + q2)) l^2 / (54 (q2 - q1)^2)
    S_ = q1**2 + q1 * q2 + q2**2
    compact = (2 * sp.sqrt(3) * S_**sp.Rational(3, 2) - 9 * q1 * q2 * (q1 + q2)) * l**2 / (54 * (q2 - q1)**2)
    for vals in ({q1: 1, q2: 2, l: 1}, {q1: 3, q2: 1, l: 2}):
        assert abs(float(pos.value.subs(vals)) - float(compact.subs(vals))) < 1e-12
    assert latex_value(pos.value).startswith(r"\frac{\left(2 \sqrt{3} \left(q_{1}^{2}")
    # Grenzfall q1 = 0: Dreieckslast, max M2 = sqrt(3) q2 l^2 / 27 bei l/sqrt(3)
    assert sp.simplify(pos.value.subs(q1, 0) - sp.sqrt(3) * q2 * l**2 / 27) == 0
    assert sp.simplify(pos.x1.subs(q1, 0) - l / sp.sqrt(3)) == 0


@pytest.mark.parametrize("sid,qty,expected", [
    ("EF01", "M2", []),
    ("EF04", "M2", [("quadratische Parabel", 0, l)]),
    ("EF07", "M2", [("kubische Parabel", 0, l)]),
    ("EF07", "Q3", [("quadratische Parabel", 0, l)]),
    ("EF08", "M2", [("kubische Parabel", 0, a), ("kubische Parabel", a, 2 * a)]),  # zwei verschiedene Kurven
    ("GT02", "M2", [("quadratische Parabel", 0, 3 * a)]),  # dieselbe Parabel über das Gelenk hinweg
])
def test_kurvenform(sid, qty, expected):
    from tm_anki.keypoints import curve_forms

    res = solve({s.id: s for s in SYSTEME}[sid].structure)
    got = [(c.name, c.x1_lo, c.x1_hi) for c in curve_forms(res, qty)]
    assert len(got) == len(expected)
    for (n, lo, hi), (n_e, lo_e, hi_e) in zip(got, expected):
        assert n == n_e and sp.simplify(lo - lo_e) == 0 and sp.simplify(hi - hi_e) == 0


def test_unabhaengige_einzelkraft_mit_streckenlast():
    from tm_anki.dsl import Kraft as K

    res = solve(balken("K3", "", L=3 * a, lager={0: Fest(), 2 * a: Los()},
                       lasten=[Strecke(0, 2 * a, q), K(3 * a, F)]).structure)
    a_v = next(r.value for r in res.reactions if r.name == "A_V")
    assert latex_value(a_v) == r"\frac{2qa - F}{2}"  # Summe positiv orientiert, Lehrbuch-Reihenfolge
    pos, _ = extremes(keypoints(res, "M2"))
    assert sp.simplify(pos.value - (2 * q * a - F)**2 / (8 * q)) == 0


@pytest.mark.parametrize("value,expected", [
    (q * l**2 / 8, r"\frac{ql^{2}}{8}"),
    (9 * q * a**2 / 32, r"\frac{9qa^{2}}{32}"),
    (-F * l, r"-F\,l"),  # schmaler Abstand: kursives F ragt sonst in das l
    (F * l / 4, r"\frac{F\,l}{4}"),
    (q0 * l**2 / (9 * sp.sqrt(3)), r"\frac{\sqrt{3}q_{0}l^{2}}{27}"),
    (-q * a / 2, r"-\frac{qa}{2}"),
    (l / 2, r"\frac{l}{2}"),
])
def test_formatter(value, expected):
    assert latex_value(value) == expected


def test_karten_und_paket(tmp_path):
    by_id = {s.id: s for s in SYSTEME}
    cards = make_cards(by_id["EF05"], fmt="svg") + make_cards(by_id["RA04"], fmt="svg")
    assert [c.note_id for c in cards] == ["EF05-Q3", "EF05-M2", "RA04-N1", "RA04-Q3", "RA04-M2"]
    for c in cards:
        assert c.front.startswith(b"<?xml") and c.back.startswith(b"<?xml")
        assert c.front_name != c.back_name
    # deterministisch: gleiches System -> gleiche Bilder -> gleiche Dateinamen (Anki-Update ohne Duplikate)
    again = make_cards(by_id["EF05"], fmt="svg")
    assert [c.back_name for c in again] == [c.back_name for c in cards[:2]]
    apkg = write_package(cards, tmp_path)
    with zipfile.ZipFile(apkg) as z:
        names = z.namelist()
    assert "collection.anki2" in names and "media" in names
