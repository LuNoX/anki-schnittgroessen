# TM-Schnittgrößen als Anki-Karten

Erzeugt ein Anki-Deck zum Üben von Schnittgrößenverläufen (Technische Mechanik / Statik).

- **Vorderseite:** System mit Lagern, Lasten, Bemaßung, x1/x3-Dreibein und gestrichelter Faser, dazu
  „Gesucht: Verlauf von N1 / Q3 / M2“. Darunter ein leeres Stabskelett als Antwortschablone.
- **Rückseite:** dasselbe Bild mit dem eingezeichneten Verlauf, exakten Kennwerten (z. B. 9qa²/32),
  ⊕/⊖, Auflagerreaktionen und Extremwerten.

Alle Werte werden exakt (symbolisch mit SymPy) berechnet. Jedes System im Katalog wird in den Tests
zusätzlich unabhängig mit einer FEM-Rechnung (anaStruct) gegengeprüft.

## Bedienung

```bash
uv sync                               # Abhängigkeiten installieren
uv run tm-anki build --preview        # Deck bauen -> build/TM_Schnittgroessen.apkg (+ build/preview.html)
uv run tm-anki check                  # alle Systeme lösen und auf Plausibilität prüfen
uv run tm-anki list                   # Katalog anzeigen
uv run tm-anki build --only "EF*,RA04"  # nur einen Teil bauen (z. B. zum Testen)
uv run pytest                         # Tests inkl. FEM-Gegenrechnung
```

Das `.apkg` in Anki über *Datei → Importieren* laden. Wird das Deck nach Änderungen neu gebaut und erneut
importiert, aktualisiert Anki die vorhandenen Karten (stabile IDs). Der Lernfortschritt bleibt dabei erhalten.

## Konventionen

- Die gestrichelte Faser markiert die positive x3-Seite. x1 läuft entlang des Stabzugs vom ersten zum
  letzten Knoten.
- Schnittgrößen sind am positiven Schnittufer positiv: N1 in +x1, Q3 in +x3, M2 dreht um +x2.
  Das heißt: M2 > 0 bedeutet Zug an der Faser.
- Positive Werte werden zur Faser hin angetragen. Damit liegt M2 immer auf der Zugseite.
  Umstellbar in [conventions.py](src/tm_anki/conventions.py) (`PLOT_SIDE`).

## Neues System hinzufügen

Systeme stehen in [src/tm_anki/katalog/](src/tm_anki/katalog/), ein Modul pro Kategorie. Ein neues System ist
eine Zeile in der passenden Liste `SYSTEME`:

```python
# gerader Balken: Positionen von links gemessen, Längen in a oder l
balken("EF17", "Einfeldträger, zwei Streckenlasten", L=3*a,
       lager={0: Fest(), 3*a: Los()},
       lasten=[Strecke(0, a, q), Strecke(2*a, 3*a, 2*q)]),

# Rahmen/Winkel/schräg: Knoten (x, y) mit y nach oben, Stabzüge mit Faserseite in Laufrichtung
rahmen("RA08", "Portalrahmen, Einzelkraft auf dem Riegel",
       knoten={"A": (0, 0), "B": (0, 2*a), "C": (2*a, 2*a), "D": (2*a, 0)},
       staebe=[Stab("A", "B", "C", "D", faser="rechts")],
       lager={"A": Fest(), "D": Los()},
       lasten=[Kraft(("B", "C", a), F)]),

# Variante eines bestehenden Systems
variante("EF05", "VA04", faser="oben"),
```

Danach `uv run tm-anki check` und `uv run pytest` ausführen, dann `uv run tm-anki build --preview`.

### Bausteine

| Baustein | Bedeutung |
|---|---|
| `Fest()`, `Los(winkel=90)`, `Einspannung()` | Lager; `Los(winkel=0)` = Loslager mit horizontaler Reaktion (an einer Wand) |
| `Kraft(pos, P, richtung="unten")` | Einzelkraft; `richtung`: `"unten"`, `"oben"`, `"links"`, `"rechts"` oder Winkel in Grad (gegen den Uhrzeigersinn ab +x, z. B. `-45`) |
| `Moment(pos, M, dreh="links")` | Einzelmoment; `"links"` = gegen den Uhrzeigersinn |
| `Strecke(von, bis, q_von, q_bis=None, richtung="unten", bezug="laenge")` | linear veränderliche Streckenlast; `bezug="projektion"` = je Grundrisslänge |
| `gelenke=[...]` | Momentengelenke (Positionen bzw. Knotennamen) |
| `faser="unten"/"oben"`, `x1="rechts"/"links"` | nur bei `balken()`: Lage der Faser und Laufrichtung |
| `Stab(..., faser="rechts"/"links")` | nur bei `rahmen()`: Faserseite in Laufrichtung |
| `gegeben=r"F = qa"` | Zusatzangabe auf der Karte (LaTeX) |
| `groessen=("M2",)` | nur bestimmte Karten erzeugen (Standard: alle Größen ≠ 0) |

Bei `rahmen()` ist eine Position ein Knotenname oder `(von, nach, abstand)` entlang eines Stabzugs.
Lasten am besten über **ein** Lastsymbol ausdrücken (z. B. `F = q*a`). `check` warnt sonst.
Statisch unbestimmte oder verschiebliche Systeme werden mit einer Fehlermeldung abgelehnt.

Eine neue Kategorie ist ein neues Modul in `katalog/` mit `KATEGORIE` und `SYSTEME`, eingetragen in
`MODULE` in [katalog/__init__.py](src/tm_anki/katalog/__init__.py).

## Aufbau

| Datei | Aufgabe |
|---|---|
| `dsl.py` | Katalog-Sprache (`balken`, `rahmen`, `variante`, Lager, Lasten) |
| `solver.py` | exakter Gleichgewichts-Solver (Starrkörper + Gelenkbolzen), Schnittgrößen-Polynome |
| `keypoints.py`, `fmt.py` | Kennwerte (Ränder, Sprünge, Extrema) und LaTeX-Formatierung |
| `render/` | Zeichnung mit matplotlib (System, Lasten, Verlauf), SVG |
| `deck.py`, `cli.py` | Anki-Paket (genanki), Vorschau, Kommandozeile |
| `checks.py` | Invarianten: Gleichgewicht, M = 0 an Gelenken, dM/dx = Q, dQ/dx = −q, Sprünge |
| `tests/anastruct_bridge.py` | Übersetzung nach anaStruct für die unabhängige FEM-Gegenrechnung |
