"""Paketprüfung (.apkg): erkennt sie echte Fehler, und ist ein frisch gebautes Deck sauber?"""

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from tm_anki.deck import make_cards, write_package
from tm_anki.decklint import html_probleme, mathjax_probleme, pruefe_paket
from tm_anki.katalog import alle_systeme

SYS = {s.id: s for s in alle_systeme()}


@pytest.fixture(name="paket", scope="module")
def fixture_paket(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("deck")
    return write_package(make_cards(SYS["EF05"]) + make_cards(SYS["RA04"]), out)


def _umbauen(src: Path, dst: Path, sql: str | None = None, ohne_medium: bool = False) -> Path:
    """Kopie des Pakets mit SQL-Änderung an der Collection bzw. ohne erstes Medium."""
    with zipfile.ZipFile(src) as z:
        inhalt = {n: z.read(n) for n in z.namelist()}
    if sql:
        db = dst.with_suffix(".anki2")
        db.write_bytes(inhalt["collection.anki2"])
        con = sqlite3.connect(db)
        con.execute(sql)
        con.commit()
        con.close()
        inhalt["collection.anki2"] = db.read_bytes()
    if ohne_medium:
        index = json.loads(inhalt["media"])
        del inhalt[next(iter(index))]
    with zipfile.ZipFile(dst, "w") as z:
        for n, data in inhalt.items():
            z.writestr(n, data)
    return dst


def test_frisches_deck_ist_sauber(paket):
    b = pruefe_paket(paket)
    assert b.ok, b.fehler
    assert not b.warnungen, b.warnungen
    assert b.notizen == 5 and b.medien == 10


@pytest.mark.parametrize(
    ("sql", "ohne_medium", "erwartet"),
    [
        (None, True, "nicht im Paket"),
        ("update col set decks = replace(decks, '1726583012', '42')", False, "Deck-ID"),
        ("update notes set guid = 'gleich'", False, "GUID doppelt"),
        (
            "update notes set flds = replace(flds, '<img', '<div><img') where id = (select min(id) from notes)",
            False,
            "HTML",
        ),
        ("update notes set flds = replace(flds, '\\)', '') where id = (select min(id) from notes)", False, "MathJax"),
        (
            "update notes set flds = substr(flds, instr(flds, char(31))) where id = (select min(id) from notes)",
            False,
            "Pflichtfeld ID",
        ),
    ],
)
def test_erkennt_kaputte_pakete(paket, tmp_path, sql, ohne_medium, erwartet):
    kaputt = _umbauen(paket, tmp_path / "kaputt.apkg", sql, ohne_medium)
    b = pruefe_paket(kaputt)
    assert not b.ok
    assert any(erwartet in f for f in b.fehler), b.fehler


def test_html_und_mathjax_hilfen():
    assert not html_probleme("<div><b>x</b><img src='a'><br></div>")
    assert html_probleme("<div><b>x</div>")
    assert not mathjax_probleme(r"\(\dfrac{q a^{2}}{8}\) und \(\{x\}\)")
    assert mathjax_probleme(r"\(\dfrac{q}{8\)")
    assert mathjax_probleme(r"\(x")
