"""Schräge Balken: Grundriss 4a, Höhe 3a, Stablänge 5a (sin/cos rational)."""

from ..dsl import F, Fest, Kraft, Los, Stab, Strecke, a, q, rahmen

KATEGORIE = "Schräger Balken"

KNOTEN = {"A": (0, 0), "B": (4 * a, 3 * a)}
STAB = [Stab("A", "B", faser="rechts")]  # Faser unten
FL = {"A": Fest(), "B": Los()}

SYSTEME = [
    rahmen("SB01", "Schräger Balken, vertikale Einzelkraft in Stabmitte", KNOTEN, STAB, FL,
           lasten=[Kraft(("A", "B", 5 * a / 2), F)]),
    rahmen("SB02", "Schräger Balken, Streckenlast je Grundrisslänge", KNOTEN, STAB, FL,
           lasten=[Strecke("A", "B", q, bezug="projektion")], gegeben=r"q\ \mathrm{je\ Grundrisslänge}"),
    rahmen("SB03", "Schräger Balken, Streckenlast je Stablänge", KNOTEN, STAB, FL,
           lasten=[Strecke("A", "B", q)], gegeben=r"q\ \mathrm{je\ Stablänge}"),
    rahmen("SB04", "Schräger Balken, Loslager an der Wand", KNOTEN, STAB, {"A": Fest(), "B": Los(winkel=0)},
           lasten=[Strecke("A", "B", q, bezug="projektion")], gegeben=r"q\ \mathrm{je\ Grundrisslänge}"),
]
