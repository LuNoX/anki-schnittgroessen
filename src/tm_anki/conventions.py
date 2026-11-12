"""Zentrale Konventionen: Bezeichnungen, Antragsrichtung, Farben, Größen.

Schnittgrößen sind am positiven Schnittufer positiv: N1 in +x1, Q3 in +x3, M2 um +x2
(fest im Solver). Hier wird nur festgelegt, wie die Verläufe *gezeichnet* werden.
"""

QUANTITIES = ("N1", "Q3", "M2")

#: LaTeX-Bezeichnung der Schnittgrößen
LATEX = {"N1": "N_1", "Q3": "Q_3", "M2": "M_2"}

#: Antragsrichtung positiver Werte: "faser" = zur gestrichelten Faser (+x3), "gegenfaser" = weg davon
PLOT_SIDE = {"N1": "faser", "Q3": "faser", "M2": "faser"}

#: Linienfarbe je Schnittgröße (Referenzpalette, Slots 1-3, alle Paare CVD-validiert)
COLORS = {"N1": "#1baf7a", "Q3": "#eb6834", "M2": "#2a78d6"}
FILL_ALPHA = 0.16

INK = "#0b0b0b"  # Text, Stäbe, Lasten
INK_MUTED = "#6b6a66"  # Faser, Bemaßung, Skelett
#: Rückseite mit Verlauf im System: Streckenlasten und Dreibein gedämpft (wiedererkennbar, nicht dominant)
SECONDARY_INK = "#a3a29c"

#: maximale Ordinate des Verlaufs relativ zur Systemgröße
DIAGRAM_SCALE = 0.22

#: Wo der Verlauf gezeichnet wird: "im_system" (direkt auf die Stäbe der Systemzeichnung),
#: "separat" (auf ein eigenes Stabskelett) oder "auto" (im System, außer es würde zu unleserlich).
#: Pro System überschreibbar mit balken(..., darstellung=...) bzw. per CLI --darstellung.
DARSTELLUNG = "auto"
#: "auto": Symbole (Lager, Lasten, Dreibein) dürfen vom Verlauf überdeckt werden; ihre Bezeichnungen
#: (A, B, F, q, M0 ...) werden aus der Fläche geschoben. Separat wird nur gezeichnet, wenn danach noch eine
#: Bezeichnung zu mehr als diesem Anteil verdeckt ist oder ein Wert des Verlaufs mit einer kollidiert.
OVERLAY_MAX_COVER = 0.05

#: Zeichen-Grundmaß (Lagergröße, Pfeillängen ...): Systemgröße / U_DIVISOR.
#: Hohe Systeme (Rahmen, schräge Balken) stehen neben ihrem Verlauf und brauchen größere Symbole.
U_DIVISOR = 18
U_DIVISOR_TALL = 13
#: Bildbreite in Zoll (Schrift bleibt dadurch auf allen Karten gleich groß); maximale Höhe
FIG_WIDTH_IN = 6.6
FIG_MAX_HEIGHT_IN = 7.5

MATH_FONTSET = "cm"
FONT_SIZE = 10
#: Schriftgröße der Werte im Verlauf; Brüche dort in voller Größe (\dfrac statt \frac)
VALUE_FONT_SIZE = 11
VALUE_FULL_SIZE_FRACTIONS = True

#: Kurzbezeichnung der Kurvenform direkt an der Kurve (nur für Grad >= 2; sonst "Grad n")
CURVE_LABELS = {2: "quadr.", 3: "kub."}
CURVE_FONT_SIZE = 9.5


def plot_sign(qty: str) -> int:
    return 1 if PLOT_SIDE[qty] == "faser" else -1
