from ..dsl import Einspannung, F, Fest, Kraft, Los, Stab, Strecke, a, q, rahmen

KATEGORIE = "Winkelträger"

WINKEL = {"A": (0, 0), "B": (0, 2 * a), "C": (a, 2 * a)}
WINKEL_STAB = [Stab("A", "B", "C", faser="rechts")]  # Faser innen

SYSTEME = [
    rahmen("WT01", "Winkelträger, vertikale Kraft am Armende", WINKEL, WINKEL_STAB, {"A": Einspannung()},
           lasten=[Kraft("C", F)]),
    rahmen("WT02", "Winkelträger, horizontale Kraft am Armende", WINKEL, WINKEL_STAB, {"A": Einspannung()},
           lasten=[Kraft("C", F, richtung="rechts")]),
    rahmen("WT03", "Winkelträger, Streckenlast auf dem Arm", WINKEL, WINKEL_STAB, {"A": Einspannung()},
           lasten=[Strecke("B", "C", q)]),
    rahmen("WT04", "Einfeldträger mit Kragstiel, Horizontalkraft am Stiel",
           {"A": (0, 0), "M": (2 * a, 0), "B": (4 * a, 0), "S": (2 * a, a)},
           [Stab("A", "M", "B", faser="rechts"), Stab("M", "S", faser="rechts")],
           {"A": Fest(), "B": Los()}, lasten=[Kraft("S", F, richtung="rechts")]),
    rahmen("WT05", "Abgewinkelter Kragarm, Horizontalkraft am Stielende",
           {"A": (0, 0), "B": (2 * a, 0), "C": (2 * a, -a)}, [Stab("A", "B", "C", faser="rechts")],
           {"A": Einspannung()}, lasten=[Kraft("C", F, richtung="rechts")]),
]
