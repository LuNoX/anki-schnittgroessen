"""Prüfung eines fertigen Anki-Pakets (.apkg), so wie Anki es beim Import sieht.

Fängt Fehler ab, die weder Solver-Tests noch Code-Linter sehen:

- Paketstruktur: Medien-Index, referenzierte und tatsächlich enthaltene Medien
- stabile IDs: Notiztyp- und Deck-ID dürfen sich nie ändern (sonst neues Deck, Lernfortschritt weg)
- Notizen: eindeutige GUIDs und Sortierfelder, Pflichtfelder gefüllt, Feldanzahl passt zum Notiztyp
- Vorlagen: jedes ``{{Feld}}`` existiert; Pflichtfelder gefüllt (bei leerer Vorderseite erzeugt Anki keine Karte)
- Inhalt: wohlgeformtes HTML, ausgeglichene MathJax-Klammern ``\\( … \\)`` und ``{ }``, gültige SVGs
- Tags ohne Leerzeichen
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from .deck import DECK_ID, FIELDS, MODEL_ID

PFLICHTFELDER = ("ID", "Titel", "Groesse", "Vorderseite", "Rueckseite")
MAX_MEDIUM_BYTES = 1_000_000  # ein einzelnes Kartenbild sollte weit darunter liegen
_TEMPLATE_FIELD = re.compile(r"{{\s*([#/^]?)\s*([^}]+?)\s*}}")
_IMG_SRC = re.compile(r'<img\s[^>]*src="([^"]+)"')
_VOID = {"img", "br", "hr", "meta", "input", "link", "wbr", "source"}
_SPECIAL_FIELDS = {"FrontSide", "Tags", "Type", "Deck", "Subdeck", "Card", "CardFlag"}


@dataclass
class Bericht:
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    notizen: int = 0
    medien: int = 0

    @property
    def ok(self) -> bool:
        return not self.fehler


class _HTMLCheck(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.probleme: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.probleme.append(f"unerwartetes </{tag}>")
            return
        self.stack.pop()

    def close(self):
        super().close()
        if self.stack:
            self.probleme.append("nicht geschlossen: " + ", ".join(f"<{t}>" for t in self.stack))


def html_probleme(text: str) -> list[str]:
    p = _HTMLCheck()
    p.feed(text)
    p.close()
    return p.probleme


def mathjax_probleme(text: str) -> list[str]:
    """Ausgeglichene ``\\( … \\)``-Paare, darin ausgeglichene geschweifte Klammern."""
    probleme = []
    if text.count("\\(") != text.count("\\)"):
        probleme.append(f"{text.count(chr(92) + '(')}x \\( gegen {text.count(chr(92) + ')')}x \\)")
        return probleme
    for formel in re.findall(r"\\\((.*?)\\\)", text, flags=re.S):
        tiefe = 0
        for i, ch in enumerate(formel):
            if ch in "{}" and i > 0 and formel[i - 1] == "\\":
                continue  # \{ \} sind Zeichen, keine Gruppen
            tiefe += {"{": 1, "}": -1}.get(ch, 0)
            if tiefe < 0:
                break
        if tiefe != 0:
            probleme.append(f"unausgeglichene {{ }} in \\({formel[:40]}…\\)")
    return probleme


def _template_felder(tmpl: str) -> set[str]:
    return {name.split(":")[-1].strip() for _, name in _TEMPLATE_FIELD.findall(tmpl)}


def pruefe_paket(apkg: Path) -> Bericht:
    b = Bericht()
    if not apkg.exists():
        b.fehler.append(f"{apkg} existiert nicht")
        return b
    with zipfile.ZipFile(apkg) as z, tempfile.TemporaryDirectory() as tmp:
        namen = set(z.namelist())
        for pflicht in ("collection.anki2", "media"):
            if pflicht not in namen:
                b.fehler.append(f"Paket ohne {pflicht}")
        if b.fehler:
            return b
        medien_index: dict[str, str] = json.loads(z.read("media"))
        medien = {name: z.read(key) for key, name in medien_index.items() if key in namen}
        for key, name in medien_index.items():
            if key not in namen:
                b.fehler.append(f"Medium {name} im Index, aber nicht im Paket")
        if len(set(medien_index.values())) != len(medien_index):
            b.fehler.append("doppelte Dateinamen im Medien-Index")

        z.extract("collection.anki2", tmp)
        con = sqlite3.connect(Path(tmp) / "collection.anki2")
        try:
            models_json, decks_json = con.execute("select models, decks from col").fetchone()
            notes = con.execute("select id, guid, mid, tags, flds from notes").fetchall()
            cards = con.execute("select nid, did from cards").fetchall()
        finally:
            con.close()

    models, decks = json.loads(models_json), json.loads(decks_json)
    _pruefe_ids_und_vorlagen(b, models, decks, cards)
    referenziert = _pruefe_notizen(b, notes)
    _pruefe_medien(b, medien, referenziert)
    b.notizen, b.medien = len(notes), len(medien)
    return b


def _pruefe_ids_und_vorlagen(b: Bericht, models: dict, decks: dict, cards: list) -> None:
    if str(MODEL_ID) not in models:
        b.fehler.append(f"Notiztyp-ID {MODEL_ID} fehlt: Anki würde einen neuen Notiztyp anlegen")
        return
    if str(DECK_ID) not in decks:
        b.fehler.append(f"Deck-ID {DECK_ID} fehlt: Anki würde ein neues Deck anlegen")
    if any(did != DECK_ID for _, did in cards):
        b.fehler.append("Karten außerhalb des Decks")
    model = models[str(MODEL_ID)]
    felder = [f["name"] for f in model["flds"]]
    if felder != FIELDS:
        b.fehler.append(f"Felder des Notiztyps {felder} passen nicht zu {FIELDS}")
    for t in model["tmpls"]:
        for teil in ("qfmt", "afmt"):
            unbekannt = _template_felder(t[teil]) - set(felder) - _SPECIAL_FIELDS
            if unbekannt:
                b.fehler.append(f"Vorlage {t['name']}/{teil}: unbekannte Felder {sorted(unbekannt)}")


def _pruefe_notizen(b: Bericht, notes: list) -> set[str]:
    referenziert: set[str] = set()
    guids: dict[str, str] = {}
    ids: set[str] = set()
    for _, guid, mid, tags, flds in notes:
        werte = flds.split("\x1f")
        kid = werte[0] if werte else "?"
        if mid != MODEL_ID:
            b.fehler.append(f"{kid}: falscher Notiztyp {mid}")
        if len(werte) != len(FIELDS):
            b.fehler.append(f"{kid}: {len(werte)} Felder statt {len(FIELDS)}")
            continue
        felder = dict(zip(FIELDS, werte))
        if kid in ids:
            b.fehler.append(f"{kid}: ID (Sortierfeld) doppelt")
        ids.add(kid)
        if guid in guids:
            b.fehler.append(f"{kid}: GUID doppelt (auch {guids[guid]})")
        guids[guid] = kid
        for name in PFLICHTFELDER:
            if not felder[name].strip():
                b.fehler.append(f"{kid}: Pflichtfeld {name} ist leer")
        for name, wert in felder.items():
            for p in html_probleme(wert):
                b.fehler.append(f"{kid}/{name}: HTML {p}")
            for p in mathjax_probleme(wert):
                b.fehler.append(f"{kid}/{name}: MathJax {p}")
            referenziert.update(_IMG_SRC.findall(wert))
        if any(" " in t for t in tags.split() if t) or not tags.strip():
            b.warnungen.append(f"{kid}: keine oder ungewöhnliche Tags {tags!r}")
    return referenziert


def _pruefe_medien(b: Bericht, medien: dict[str, bytes], referenziert: set[str]) -> None:
    for name in sorted(referenziert - medien.keys()):
        b.fehler.append(f"Medium {name} wird referenziert, fehlt aber im Paket")
    for name in sorted(medien.keys() - referenziert):
        b.warnungen.append(f"Medium {name} ist im Paket, wird aber nicht verwendet")
    for name, data in medien.items():
        if len(data) > MAX_MEDIUM_BYTES:
            b.warnungen.append(f"Medium {name} ist {len(data) // 1024} KiB groß")
        if name.endswith(".svg"):
            try:
                root = ET.fromstring(data)
            except ET.ParseError as exc:
                b.fehler.append(f"SVG {name} ist kein gültiges XML: {exc}")
                continue
            if not root.tag.endswith("svg") or "viewBox" not in root.attrib:
                b.fehler.append(f"SVG {name}: Wurzel <svg> mit viewBox erwartet")
        elif name.endswith(".png") and not data.startswith(b"\x89PNG\r\n\x1a\n"):
            b.fehler.append(f"PNG {name} hat keine PNG-Signatur")


__all__ = ["Bericht", "html_probleme", "mathjax_probleme", "pruefe_paket"]
