"""Anki-Deck (genanki): Notiztyp, Karten-HTML, Medien, stabile IDs."""

from __future__ import annotations

import hashlib
import html
import math
from dataclasses import dataclass
from pathlib import Path

import genanki
import sympy as sp

from . import conventions as cv
from .fmt import complex_extrema, latex_value
from .keypoints import keypoints
from .model import SystemDef
from .render import render_card
from .solver import Result, solve
from .symbols import num

# Feste IDs: nicht ändern, sonst legt Anki beim Import ein neues Deck/einen neuen Notiztyp an.
MODEL_ID = 1_726_583_011
DECK_ID = 1_726_583_012
DECK_NAME = "Technische Mechanik::Schnittgrößen"
TAG_PREFIX = "TM::Schnittgroessen"

CSS = """
.card {
  font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  font-size: 18px; text-align: center; color: #0b0b0b; background: #fcfcfb;
}
.tm-card { max-width: 900px; margin: 0 auto; }
.tm-title { font-size: .8em; color: #52514e; margin-bottom: .25em; }
.tm-ask { font-size: 1.15em; font-weight: 600; margin-bottom: .25em; }
.tm-given { font-size: .95em; margin-bottom: .35em; }
.tm-img img { max-width: 100%; height: auto; }
.tm-info { display: inline-block; text-align: left; font-size: .9em; margin-top: .6em; }
.tm-info ul { margin: .15em 0 .5em 1.2em; padding: 0; }
.tm-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25em 1.6em; margin: .15em 0 .5em 0; }
.tm-row span { white-space: nowrap; }
.tm-sec { font-weight: 600; margin-top: .35em; }
.tm-id { font-size: .7em; color: #6b6a66; margin-top: 1em; }
.card.nightMode, .card.night_mode { background: #1a1a19; color: #f0efec; }
.nightMode .tm-title, .night_mode .tm-title { color: #c3c2b7; }
.nightMode .tm-img img, .night_mode .tm-img img { filter: invert(1) hue-rotate(180deg); }
"""

_HEAD = """<div class="tm-card">
<div class="tm-title">{{Titel}}</div>
<div class="tm-ask">%s {{Groesse}}</div>
{{#Gegeben}}<div class="tm-given">Gegeben: {{Gegeben}}</div>{{/Gegeben}}
"""

FRONT = _HEAD % "Gesucht: Verlauf von" + """<div class="tm-img">{{Vorderseite}}</div>
</div>"""

BACK = _HEAD % "Verlauf von" + """<div class="tm-img">{{Rueckseite}}</div>
<div class="tm-info">{{Info}}</div>
<div class="tm-id">{{ID}} · {{Kategorie}}</div>
</div>"""

FIELDS = ["ID", "Titel", "Kategorie", "Groesse", "Gegeben", "Vorderseite", "Rueckseite", "Info"]

MODEL = genanki.Model(
    MODEL_ID,
    "TM Schnittgröße",
    fields=[{"name": f} for f in FIELDS],
    templates=[{"name": "Verlauf", "qfmt": FRONT, "afmt": BACK}],
    css=CSS,
    sort_field_index=0,
)


class TMNote(genanki.Note):
    @property
    def guid(self):  # stabil über Neubauten hinweg -> Lernfortschritt bleibt erhalten
        return genanki.guid_for(self.fields[0])


# --------------------------------------------------------------------------- Karteninhalt


@dataclass
class Card:
    sysdef_id: str
    titel: str
    kategorie: str
    qty: str
    gegeben: str
    info: str
    front_name: str
    back_name: str
    front: bytes
    back: bytes

    @property
    def note_id(self) -> str:
        return f"{self.sysdef_id}-{self.qty}"


_ARROWS = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]


def _arrow(dx: float, dy: float) -> str:
    ang = math.degrees(math.atan2(dy, dx)) % 360
    return _ARROWS[int(((ang + 22.5) % 360) // 45)]


def _name_tex(name: str) -> str:
    if "_" not in name:
        return name
    base, sub = name.split("_", 1)
    return f"{base}_{{\\mathrm{{{sub}}}}}" if sub in ("H", "V") else f"{base}_{{{sub}}}"


def info_html(result: Result, qty: str, kps: list) -> str:
    """Auflagerreaktionen. Kennwerte, Kurvenform und Lage der Extrema stehen direkt im Verlauf;
    nur Ausdrücke, die dafür zu lang sind (z. B. allgemeine Trapezlast), werden hier ausgeschrieben."""
    items = []
    for rv in result.reactions:
        v = sp.simplify(rv.value)
        name = _name_tex(rv.name)
        if num(v) == 0:
            items.append(f"\\({name} = 0\\)")
            continue
        mag = latex_value(-v if num(v) < 0 else v)
        if rv.direction is None:
            arrow = "↺" if num(v) > 0 else "↻"
        else:
            sgn = 1 if num(v) > 0 else -1
            arrow = _arrow(sgn * num(rv.direction[0]), -sgn * num(rv.direction[1]))
        items.append(f"\\({name} = {mag}\\) {arrow}")
    parts = [_row("Auflagerreaktionen", items)]

    q_tex = cv.LATEX[qty]
    rows = []
    for kp, dist, name in complex_extrema(result, kps):
        label = "\\max" if num(kp.value) > 0 else "\\min"
        rows.append(f"\\({label} {q_tex} = {latex_value(kp.value)}\\)")
        if name:
            rows.append(f"\\({name} = {latex_value(dist)}\\)")
    if rows:
        parts.append(_row(f"Extremum \\({q_tex}\\) (bei \\({cv.ZERO_OF_SLOPE[qty]}\\))", rows))
    return "".join(parts)


#: Layout auch inline, damit es schon greift, wenn Anki den Notiztyp (CSS) beim Import nicht aktualisiert.
#: Grundlinie statt Oberkante, damit kurze (A_H = 0) und hohe Einträge (Brüche) auf einer Linie stehen.
_ROW_STYLE = "display:flex;flex-wrap:wrap;align-items:baseline;gap:.25em 1.6em"


def _row(title: str, items: list[str]) -> str:
    """Überschrift + Einträge nebeneinander (bricht bei Platzmangel zwischen Einträgen um)."""
    spans = "".join(f'<span style="white-space:nowrap">{i}</span>' for i in items)
    return f'<div class="tm-sec">{title}</div><div class="tm-row" style="{_ROW_STYLE}">{spans}</div>'


def _media_name(sid: str, qty: str, side: str, data: bytes, fmt: str) -> str:
    digest = hashlib.sha1(data).hexdigest()[:8]
    return f"tm_{sid}_{qty}_{side}_{digest}.{fmt}"


def make_cards(sysdef: SystemDef, fmt: str = "svg") -> list[Card]:
    result = solve(sysdef.structure)
    qtys = sysdef.groessen or result.nonzero_quantities()
    cards = []
    for qty in qtys:
        kps = keypoints(result, qty)
        front, back = render_card(sysdef, result, qty, kps, fmt=fmt)
        cards.append(Card(
            sysdef_id=sysdef.id,
            titel=sysdef.titel,
            kategorie=sysdef.kategorie,
            qty=qty,
            gegeben=f"\\({sysdef.gegeben}\\)" if sysdef.gegeben else "",
            info=info_html(result, qty, kps),
            front_name=_media_name(sysdef.id, qty, "front", front, fmt),
            back_name=_media_name(sysdef.id, qty, "back", back, fmt),
            front=front,
            back=back,
        ))
    return cards


def _titel_html(titel: str) -> str:
    # $...$ im Titel (z. B. bei Varianten) für MathJax umsetzen
    out, inside = [], False
    for part in html.escape(titel).split("$"):
        out.append(f"\\({part}\\)" if inside else part)
        inside = not inside
    return "".join(out)


def write_package(cards: list[Card], out_dir: Path) -> Path:
    media_dir = out_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    for old in media_dir.glob("tm_*"):
        old.unlink()
    deck = genanki.Deck(DECK_ID, DECK_NAME)
    media = []
    for c in cards:
        for name, data in ((c.front_name, c.front), (c.back_name, c.back)):
            path = media_dir / name
            path.write_bytes(data)
            media.append(str(path))
        tag_kat = c.kategorie.replace(" ", "_")
        deck.add_note(TMNote(
            model=MODEL,
            fields=[c.note_id, _titel_html(c.titel), html.escape(c.kategorie), f"\\({cv.LATEX[c.qty]}\\)",
                    c.gegeben, f'<img src="{c.front_name}">', f'<img src="{c.back_name}">', c.info],
            tags=[f"{TAG_PREFIX}::{tag_kat}", f"{TAG_PREFIX}::{c.qty}"],
        ))
    pkg = genanki.Package(deck)
    pkg.media_files = media
    target = out_dir / "TM_Schnittgroessen.apkg"
    pkg.write_to_file(str(target))
    return target


PREVIEW_HEAD = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TM Schnittgrößen – Vorschau</title>
<script>window.MathJax = {tex: {inlineMath: [['\\\\(', '\\\\)']]}};</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js" async></script>
<style>
body { font-family: system-ui, sans-serif; background: #fcfcfb; color: #0b0b0b; margin: 16px; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; border-top: 1px solid #ddd; padding: 12px 0; }
.row img { width: 100%; height: auto; }
.meta { grid-column: 1 / -1; display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.meta b { font-size: 1.1em; } .info { font-size: .9em; }
.tm-sec { font-weight: 600; margin-top: .35em; }
.tm-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25em 1.6em; margin: .15em 0 .5em 0; }
.tm-row span { white-space: nowrap; }
@media (max-width: 800px) { .row { grid-template-columns: 1fr; } }
</style></head><body><h1>TM Schnittgrößen – Vorschau</h1>
"""


def write_preview(cards: list[Card], out_dir: Path) -> Path:
    rows = []
    for c in cards:
        rows.append(
            f'<div class="row" id="{c.note_id}"><div class="meta"><b>{c.note_id}</b>'
            f"<span>{_titel_html(c.titel)}</span><span>Gesucht: \\({cv.LATEX[c.qty]}\\)</span>"
            f"<span>{c.gegeben}</span></div>"
            f'<div><img src="media/{c.front_name}" alt="Vorderseite {c.note_id}"></div>'
            f'<div><img src="media/{c.back_name}" alt="Rückseite {c.note_id}"><div class="info">{c.info}</div></div>'
            "</div>"
        )
    target = out_dir / "preview.html"
    target.write_text(PREVIEW_HEAD + "\n".join(rows) + "</body></html>", encoding="utf-8")
    return target


__all__ = ["make_cards", "write_package", "write_preview"]
