from ..dsl import F, Fest, Kraft, Los, Stab, Strecke, a, q, rahmen

KATEGORIE = "Rahmen"

PORTAL = {"A": (0, 0), "B": (0, 2 * a), "C": (2 * a, 2 * a), "D": (2 * a, 0)}
PORTAL_STAB = [Stab("A", "B", "C", "D", faser="rechts")]  # Faser innen
FL = {"A": Fest(), "D": Los()}

DREI = {"A": (0, 0), "B": (0, 2 * a), "G": (a, 2 * a), "C": (2 * a, 2 * a), "D": (2 * a, 0)}
DREI_STAB = [Stab("A", "B", "G", "C", "D", faser="rechts")]
FF = {"A": Fest(), "D": Fest()}

SYSTEME = [
    rahmen("RA01", "Portalrahmen, Horizontalkraft an der linken Ecke", PORTAL, PORTAL_STAB, FL,
           lasten=[Kraft("B", F, richtung="rechts")]),
    rahmen("RA02", "Portalrahmen, Streckenlast auf dem Riegel", PORTAL, PORTAL_STAB, FL,
           lasten=[Strecke("B", "C", q)]),
    rahmen("RA03", "Portalrahmen, horizontale Streckenlast auf dem linken Stiel", PORTAL, PORTAL_STAB, FL,
           lasten=[Strecke("A", "B", q, richtung="rechts")]),
    rahmen("RA04", "Dreigelenkrahmen, Einzelkraft im Firstgelenk", DREI, DREI_STAB, FF, gelenke=["G"],
           lasten=[Kraft("G", F)]),
    rahmen("RA05", "Dreigelenkrahmen, Streckenlast auf dem Riegel", DREI, DREI_STAB, FF, gelenke=["G"],
           lasten=[Strecke("B", "C", q)]),
    rahmen("RA06", "Dreigelenkrahmen, Horizontalkraft an der linken Ecke", DREI, DREI_STAB, FF, gelenke=["G"],
           lasten=[Kraft("B", F, richtung="rechts")]),
    rahmen("RA07", "Portalrahmen mit Riegelüberstand, Einzelkraft am Kragende",
           {**PORTAL, "E": (3 * a, 2 * a)}, [*PORTAL_STAB, Stab("C", "E", faser="rechts")], FL,
           lasten=[Kraft("E", F)]),
]
