from ..dsl import Einspannung, F, Kraft, M0, Moment, Strecke, a, balken, l, q, q0

KATEGORIE = "Kragarm"

LINKS = {0: Einspannung()}

SYSTEME = [
    balken("KA01", "Kragarm, Einzelkraft am freien Ende", L=l, lager=LINKS, lasten=[Kraft(l, F)]),
    balken("KA02", "Kragarm, Einzelkraft in der Mitte", L=2 * a, lager=LINKS, lasten=[Kraft(a, F)]),
    balken("KA03", "Kragarm, Gleichstreckenlast", L=l, lager=LINKS, lasten=[Strecke(0, l, q)]),
    balken("KA04", "Kragarm, Streckenlast auf der äußeren Hälfte", L=2 * a, lager=LINKS,
           lasten=[Strecke(a, 2 * a, q)]),
    balken("KA05", "Kragarm, Dreieckslast mit Maximum an der Einspannung", L=l, lager=LINKS,
           lasten=[Strecke(0, l, q0, 0)]),
    balken("KA06", "Kragarm, Dreieckslast mit Maximum am freien Ende", L=l, lager=LINKS,
           lasten=[Strecke(0, l, 0, q0)]),
    balken("KA07", "Kragarm, Einzelmoment am freien Ende", L=l, lager=LINKS, lasten=[Moment(l, M0)]),
    balken("KA08", "Kragarm, schräge Einzelkraft am freien Ende", L=l, lager=LINKS,
           lasten=[Kraft(l, F, richtung=-135)], gegeben=r"\alpha = 45^\circ"),
    balken("KA09", "Kragarm, Zugkraft am freien Ende", L=l, lager=LINKS,
           lasten=[Kraft(l, F, richtung="rechts")]),
    balken("KA10", "Kragarm, Einspannung rechts, Einzelkraft", L=l, lager={l: Einspannung()},
           lasten=[Kraft(0, F)]),
    balken("KA11", "Kragarm, Einspannung rechts, Gleichstreckenlast", L=l, lager={l: Einspannung()},
           lasten=[Strecke(0, l, q)]),
]
