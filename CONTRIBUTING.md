# Mitmachen

Dir fehlt ein System im Deck, etwa aus einer Altklausur, einer Übung oder dem Skript? **Trag es einfach
selbst ein. Neue Systeme sind ausdrücklich erwünscht und werden gerne als Pull Request übernommen.** Je
mehr typische Fälle das Deck abdeckt, desto besser lässt sich damit üben.

## Ein System ist eine Zeile

Du musst weder den Solver noch die Zeichnung anfassen. Ein System beschreibst du so, wie du es auf Papier
skizzieren würdest: Länge, Lager, Gelenke, Lasten. So sieht zum Beispiel der Gerberträger GT01 aus:

```python
balken("GT01", "Gerberträger, Einzelkraft im Einhängeträger", L=3*a,
       lager={0: Einspannung(), 3*a: Los()}, gelenke=[a],
       lasten=[Kraft(2*a, F)]),
```

Alles andere wird automatisch erzeugt: Auflagerreaktionen, Verläufe, Kennwerte, Zeichnung und Karten.
Danach prüft eine unabhängige FEM-Rechnung, ob die Werte stimmen. Ein Fehler im eigenen System fällt also
spätestens bei `uv run pytest` auf. Wer TM gerade lernt, ist damit gut gerüstet, und nebenbei ist das eine
gute Übung im Freischneiden.

Alle Bausteine (Lager, Kräfte, Momente, Streckenlasten, Rahmen mit Knoten) stehen im README im Abschnitt
[Neues System hinzufügen](README.md#neues-system-hinzufügen). Als Vorlage eignet sich ein ähnliches
System aus dem [Katalog](src/tm_anki/katalog/).

## Ablauf

Voraussetzungen: Git und [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.13
und alle Abhängigkeiten installiert uv selbst.

> **Neu bei Git und GitHub?**
> Eine Schritt für Schritt Erklärung zum allgemeinen Ablauf mit Forks, Branches und Pull Requests anhand eines Übungsrepos findest du [hier](https://github.com/firstcontributions/first-contributions/blob/main/docs/translations/README.de.md) und die GitHub-Dokumentation zum Beitragen zu Open Source Projekten [hier](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-open-source).

1. Repo forken, klonen und einrichten:
   ```bash
   git clone https://github.com/DEIN-NAME/anki-schnittgroessen.git
   cd anki-schnittgroessen
   uv sync
   git switch -c system-ef17
   ```
2. System in das passende Modul unter [src/tm_anki/katalog/](src/tm_anki/katalog/) eintragen. Neue
   Bausteine gehören in die `import`-Zeile des Moduls. Die ID besteht aus dem Präfix der Kategorie und der
   nächsten freien Nummer (`uv run tm-anki list`):

   | Präfix | Kategorie |
   |---|---|
   | `EF` | Einfeldträger |
   | `KA` | Kragarm |
   | `UE` | Träger mit Überstand |
   | `GT` | Gerberträger |
   | `VA` | Vorzeichen-Varianten |
   | `SB` | schräge Balken |
   | `WT` | Winkelträger |
   | `RA` | Rahmen |

   Passt nichts, lege eine neue Kategorie an (siehe README).
3. Prüfen:
   ```bash
   uv run tm-anki check                          # alle Systeme lösen, Gleichgewicht und Invarianten
   uv run pytest                                 # Tests inkl. FEM-Gegenrechnung jedes Katalogsystems
   uv run tm-anki build --only "EF17" --preview  # -> build/preview.html
   ```
   In der Vorschau Vorder- und Rückseite ansehen. Sind die Beschriftungen lesbar und die Werte plausibel?
4. Committen, pushen und einen Pull Request gegen `main` öffnen. `build/` ist ignoriert. Im Pull Request
   laufen automatisch die Tests. Ein Bot kommentiert den Karten-Diff mit neuen, entfernten und geänderten
   Karten, bei Änderungen mit Vorher-nachher-Bildern.

### Worauf es bei einem System ankommt

- **Statisch bestimmt:** Der Solver lehnt statisch unbestimmte und verschiebliche Systeme ab. Solche
  Systeme liegen bewusst außerhalb des Umfangs.
- **Allgemeine Lasten:** Verwende unabhängige Lastsymbole (`F` und `q` statt `F = 2kN`), damit die Karte
  allgemein bleibt. Hängt die Form des Verlaufs vom Lastverhältnis ab, gehört die gezeichnete Bedingung
  in `gegeben`, z. B. `gegeben=r"F < 2qa"`.
- **Kurze Titel:** Was in der Zeichnung zu sehen ist.
- **Lernwert:** Am meisten bringen Systeme, die ein neues Muster zeigen, also einen anderen Lagertyp,
  eine andere Lastform oder eine typische Klausurfalle. Ein reines Duplikat mit anderen Zahlen bringt wenig.
- **Hinweis bei Bedarf:** Lässt sich die Lösung mit einem Trick schneller finden (z. B. Überlagerung),
  kann ein `hinweis="…"` auf der Rückseite helfen.

### Hängst du fest?

Lehnt der Solver dein System ab oder sieht die Karte seltsam aus, öffne trotzdem einen Pull Request, gern
als Draft. Beschreib kurz, wo es hakt. Dann schauen wir gemeinsam drauf.

## Fehler melden

Ist ein Wert falsch oder eine Karte schwer lesbar, öffne bitte ein Issue mit:

- der Karten-ID (z. B. `RA05-M2`, steht im Sortierfeld der Karte)
- dem Fehler und, falls möglich, deiner eigenen Rechnung
- bei Darstellungsproblemen einem Screenshot

## Andere Änderungen

Verbesserungen an Solver, Zeichnung oder Deck sind ebenfalls willkommen. Bei größeren Umbauten öffne bitte
vorher ein Issue, damit wir die Idee kurz abstimmen können. Für jede Änderung gilt: Tests und Linter
müssen grün sein (siehe README, Abschnitt [Entwicklung](README.md#entwicklung)). Am einfachsten richtest du
einmal `uv run pre-commit install` ein, dann laufen die Prüfungen bei jedem Commit automatisch.

## Lizenz

Mit deinem Beitrag stimmst du zu, dass er unter der [Apache License 2.0](LICENSE) veröffentlicht wird,
wie der Rest des Projekts.
