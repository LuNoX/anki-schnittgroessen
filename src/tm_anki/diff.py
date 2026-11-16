"""Karten-Diff zwischen zwei Builds (für Pull Requests).

Liest die ``TM_Schnittgroessen.apkg`` zweier Build-Ordner und erzeugt einen Markdown-Kommentar mit neuen,
entfernten und geänderten Karten. Die Bilder heißen nach ihrem Inhalts-Hash, eine geänderte Zeichnung hat
also einen anderen Dateinamen. Bilder werden nach ``<out>/img`` kopiert und im Markdown als ``{{IMG}}/<name>``
referenziert. Der Platzhalter wird im Workflow durch die URL ersetzt, unter der die Bilder liegen.

Bewusst nur auf Basis der .apkg-Datei: Der Basis-Build stammt vom Ziel-Branch und kennt dieses Modul evtl.
noch nicht.
"""

from __future__ import annotations

import difflib
import html
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .deck import FIELDS

MARKER = "<!-- anki-karten-diff -->"
IMG = "{{IMG}}"
APKG = "TM_Schnittgroessen.apkg"
MAX_BILDKARTEN = 30  # mehr Karten mit Bildern machen den Kommentar unübersichtlich (und zu lang)
MAX_ZEICHEN = 60_000  # GitHub erlaubt 65 536 Zeichen pro Kommentar
BILD_BREITE = 380

_IMG_SRC = re.compile(r'<img src="([^"]+)"')
_TAG = re.compile(r"<[^>]+>")


@dataclass
class Karte:
    id: str
    felder: dict[str, str]
    vorne: str | None = None
    hinten: str | None = None

    @property
    def titel(self) -> str:
        return _text(self.felder.get("Titel", ""))


@dataclass
class Diff:
    neu: list[Karte] = field(default_factory=list)
    entfernt: list[Karte] = field(default_factory=list)
    geaendert: list[tuple[Karte, Karte, list[str]]] = field(default_factory=list)
    unveraendert: int = 0


def _text(s: str) -> str:
    return html.unescape(_TAG.sub("", s)).strip()


def lies_deck(build_dir: Path) -> dict[str, Karte]:
    """Karten eines Builds, nach ID. Fehlt das Paket (z. B. Basis-Build fehlgeschlagen): leer."""
    apkg = build_dir / APKG
    if not apkg.exists():
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(apkg) as z:
            z.extract("collection.anki2", tmp)
        con = sqlite3.connect(Path(tmp) / "collection.anki2")
        try:
            rows = [r[0] for r in con.execute("select flds from notes")]
        finally:
            con.close()
    karten = {}
    for flds in rows:
        werte = flds.split("\x1f")
        felder = dict(zip(FIELDS, werte))
        k = Karte(werte[0], felder)
        for name, attr in (("Vorderseite", "vorne"), ("Rueckseite", "hinten")):
            m = _IMG_SRC.search(felder.get(name, ""))
            setattr(k, attr, m.group(1) if m else None)
        karten[k.id] = k
    return karten


def vergleiche(alt: dict[str, Karte], neu: dict[str, Karte]) -> Diff:
    d = Diff()
    for kid, k in neu.items():
        if kid not in alt:
            d.neu.append(k)
            continue
        a = alt[kid]
        geaendert = [f for f in FIELDS if a.felder.get(f) != k.felder.get(f)]
        if geaendert:
            d.geaendert.append((a, k, geaendert))
        else:
            d.unveraendert += 1
    d.entfernt = [k for kid, k in alt.items() if kid not in neu]
    return d


_ANZEIGE = {
    "Vorderseite": "Vorderseite",
    "Rueckseite": "Rückseite",
    "Info": "Werte/Hinweis",
    "Titel": "Titel",
    "Gegeben": "Gegeben",
    "Kategorie": "Kategorie",
    "Groesse": "Größe",
}


def _bild(name: str | None, quelle: Path, ziel: Path, kopiert: set[str]) -> str:
    if not name:
        return "–"
    src = quelle / "media" / name
    if not src.exists():
        return f"`{name}` fehlt"
    if name not in kopiert:
        shutil.copy2(src, ziel / name)
        kopiert.add(name)
    return f'<img src="{IMG}/{name}" width="{BILD_BREITE}">'


def _textdiff(a: str, b: str) -> str:
    def zeilen(s):
        s = re.sub(r"</(div|p)>|<br\s*/?>", "\n", s)
        return [z.strip() for z in _text(s).splitlines() if z.strip()]

    diff = list(difflib.unified_diff(zeilen(a), zeilen(b), lineterm="", n=0))[2:]
    diff = [z for z in diff if not z.startswith("@@")]
    return "```diff\n" + "\n".join(diff) + "\n```" if diff else ""


def schreibe_kommentar(base: Path, head: Path, out: Path, basis_fehlt: bool = False) -> Diff:
    alt, neu = lies_deck(base), lies_deck(head)
    d = vergleiche(alt, neu)
    img = out / "img"
    img.mkdir(parents=True, exist_ok=True)
    kopiert: set[str] = set()
    bildkarten = 0

    teile = [MARKER, "## Karten-Diff", ""]
    if basis_fehlt or not alt:
        teile += ["> ⚠️ Der Ziel-Branch ließ sich nicht bauen, daher erscheinen alle Karten als neu.", ""]
    teile.append(
        f"**{len(d.neu)} neu · {len(d.entfernt)} entfernt · {len(d.geaendert)} geändert** · "
        f"{d.unveraendert} unverändert"
    )
    if not (d.neu or d.entfernt or d.geaendert):
        teile += ["", "Keine Änderungen an den Karten."]

    def mit_bildern() -> bool:
        nonlocal bildkarten
        bildkarten += 1
        return bildkarten <= MAX_BILDKARTEN

    if d.neu:
        teile += ["", f"### Neu ({len(d.neu)})", ""]
        for k in d.neu:
            if mit_bildern():
                teile += [
                    f"<details open><summary><b>{k.id}</b> · {html.escape(k.titel)}</summary>",
                    "",
                    "| Vorderseite | Rückseite |",
                    "|---|---|",
                    f"| {_bild(k.vorne, head, img, kopiert)} | {_bild(k.hinten, head, img, kopiert)} |",
                    "",
                    "</details>",
                    "",
                ]
            else:
                teile.append(f"- **{k.id}** · {k.titel}")

    if d.geaendert:
        teile += ["", f"### Geändert ({len(d.geaendert)})", ""]
        for a, k, felder in d.geaendert:
            was = ", ".join(_ANZEIGE.get(f, f) for f in felder)
            if not mit_bildern():
                teile.append(f"- **{k.id}** · {k.titel} ({was})")
                continue
            teile += [f"<details open><summary><b>{k.id}</b> · {html.escape(k.titel)} ({was})</summary>", ""]
            seiten = [
                s
                for s in (("Vorderseite", "vorne", "Vorderseite"), ("Rueckseite", "hinten", "Rückseite"))
                if s[0] in felder
            ]
            if seiten:
                teile += ["| | vorher | nachher |", "|---|---|---|"]
                for _, attr, name in seiten:
                    teile.append(
                        f"| {name} | {_bild(getattr(a, attr), base, img, kopiert)} | "
                        f"{_bild(getattr(k, attr), head, img, kopiert)} |"
                    )
                teile.append("")
            for f in ("Titel", "Gegeben", "Info"):
                if f in felder and (td := _textdiff(a.felder.get(f, ""), k.felder.get(f, ""))):
                    teile += [f"**{_ANZEIGE[f]}**", "", td, ""]
            teile += ["</details>", ""]

    if d.entfernt:
        teile += ["", f"### Entfernt ({len(d.entfernt)})", ""]
        teile += [f"- **{k.id}** · {k.titel}" for k in d.entfernt]

    if bildkarten > MAX_BILDKARTEN:
        teile += ["", f"_Bilder nur für die ersten {MAX_BILDKARTEN} Karten, die übrigen sind nur aufgelistet._"]

    text = "\n".join(teile) + "\n"
    if len(text) > MAX_ZEICHEN:
        text = text[:MAX_ZEICHEN] + "\n\n_… gekürzt, der Kommentar wäre für GitHub zu lang._\n"
    (out / "comment.md").write_text(text, encoding="utf-8")
    return d


__all__ = ["Diff", "Karte", "lies_deck", "schreibe_kommentar", "vergleiche"]
