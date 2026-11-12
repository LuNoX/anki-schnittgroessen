from ..dsl import F, Fest, Kraft, Los, M0, Moment, Strecke, a, balken, q

KATEGORIE = "Träger mit Überstand"

EINSEITIG = {0: Fest(), 2 * a: Los()}
BEIDSEITIG = {a: Fest(), 3 * a: Los()}

SYSTEME = [
    balken("UE01", "Träger mit Kragarm, Einzelkraft am Kragende", L=3 * a, lager=EINSEITIG,
           lasten=[Kraft(3 * a, F)]),
    balken("UE02", "Träger mit Kragarm, Gleichstreckenlast", L=3 * a, lager=EINSEITIG,
           lasten=[Strecke(0, 3 * a, q)]),
    balken("UE03", "Träger mit Kragarm, Streckenlast auf dem Kragarm", L=3 * a, lager=EINSEITIG,
           lasten=[Strecke(2 * a, 3 * a, q)]),
    balken("UE04", "Träger mit Kragarm, Streckenlast im Feld und Kraft am Kragende", L=3 * a,
           lager=EINSEITIG, lasten=[Strecke(0, 2 * a, q), Kraft(3 * a, q * a, label="F")], gegeben=r"F = qa"),
    balken("UE05", "Träger mit Kragarm, Einzelmoment am Kragende", L=3 * a, lager=EINSEITIG,
           lasten=[Moment(3 * a, M0)]),
    balken("UE06", "Träger mit beidseitigem Überstand, Kräfte an den Enden", L=4 * a, lager=BEIDSEITIG,
           lasten=[Kraft(0, F), Kraft(4 * a, F)]),
    balken("UE07", "Träger mit beidseitigem Überstand, Gleichstreckenlast", L=4 * a, lager=BEIDSEITIG,
           lasten=[Strecke(0, 4 * a, q)]),
]
