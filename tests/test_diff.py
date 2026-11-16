"""Karten-Diff für Pull Requests."""

from tm_anki.deck import make_cards, write_package
from tm_anki.diff import IMG, MARKER, lies_deck, schreibe_kommentar
from tm_anki.katalog import alle_systeme

SYS = {s.id: s for s in alle_systeme()}


def _build(tmp_path, name, cards):
    out = tmp_path / name
    write_package(cards, out)
    return out


def test_diff_neu_entfernt_geaendert(tmp_path):
    ef05 = make_cards(SYS["EF05"], fmt="svg", darstellung="im_system")
    ef05_sep = make_cards(SYS["EF05"], fmt="svg", darstellung="separat")  # andere Rückseite
    kragarm = make_cards(SYS["KA01"], fmt="svg")
    gerber = make_cards(SYS["GT04"], fmt="svg")

    base = _build(tmp_path, "base", ef05 + kragarm)
    head = _build(tmp_path, "head", ef05_sep + gerber)
    assert set(lies_deck(base)) == {c.note_id for c in ef05 + kragarm}

    out = tmp_path / "diff"
    d = schreibe_kommentar(base, head, out)
    assert {k.id for k in d.neu} == {c.note_id for c in gerber}
    assert {k.id for k in d.entfernt} == {c.note_id for c in kragarm}
    assert {k.id for _, k, _ in d.geaendert} == {c.note_id for c in ef05}
    assert all("Rueckseite" in felder for _, _, felder in d.geaendert)

    text = (out / "comment.md").read_text(encoding="utf-8")
    assert text.startswith(MARKER)
    assert "### Neu" in text and "### Entfernt" in text and "### Geändert" in text
    # jedes referenzierte Bild liegt im img-Ordner
    for name in {c.back_name for c in ef05 + ef05_sep} | {c.front_name for c in gerber}:
        assert f"{IMG}/{name}" in text
        assert (out / "img" / name).exists()


def test_diff_ohne_aenderung_und_ohne_basis(tmp_path):
    cards = make_cards(SYS["EF01"], fmt="svg")
    a = _build(tmp_path, "a", cards)
    b = _build(tmp_path, "b", make_cards(SYS["EF01"], fmt="svg"))
    d = schreibe_kommentar(a, b, tmp_path / "d1")
    assert not (d.neu or d.entfernt or d.geaendert) and d.unveraendert == len(cards)
    assert "Keine Änderungen" in (tmp_path / "d1" / "comment.md").read_text(encoding="utf-8")

    d = schreibe_kommentar(tmp_path / "gibtsnicht", b, tmp_path / "d2", basis_fehlt=True)
    assert len(d.neu) == len(cards)
    assert "ließ sich nicht bauen" in (tmp_path / "d2" / "comment.md").read_text(encoding="utf-8")
