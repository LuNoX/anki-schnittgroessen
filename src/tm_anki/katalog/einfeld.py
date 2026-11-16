from ..dsl import M0, F, Fest, Kraft, Los, Moment, Strecke, a, balken, l, q, q0, q1, q2

KATEGORIE = "Einfeldträger"


def fl(L):
    """Festlager links, Loslager rechts."""
    return {0: Fest(), L: Los()}


SYSTEME = [
    balken("EF01", "Einfeldträger, Einzelkraft in Feldmitte", L=l, lager=fl(l), lasten=[Kraft(l / 2, F)]),
    balken("EF02", "Einfeldträger, Einzelkraft außermittig", L=3 * a, lager=fl(3 * a), lasten=[Kraft(a, F)]),
    balken("EF03", "Einfeldträger, zwei Einzelkräfte", L=3 * a, lager=fl(3 * a),
           lasten=[Kraft(a, F), Kraft(2 * a, F)]),
    balken("EF04", "Einfeldträger, Gleichstreckenlast", L=l, lager=fl(l), lasten=[Strecke(0, l, q)]),
    balken("EF05", "Einfeldträger, Streckenlast auf der linken Hälfte", L=2 * a, lager=fl(2 * a),
           lasten=[Strecke(0, a, q)]),
    balken("EF06", "Einfeldträger, Streckenlast im mittleren Drittel", L=3 * a, lager=fl(3 * a),
           lasten=[Strecke(a, 2 * a, q)]),
    balken("EF07", "Einfeldträger, Dreieckslast", L=l, lager=fl(l), lasten=[Strecke(0, l, 0, q0)]),
    balken("EF08", "Einfeldträger, Dreieckslast mit Spitze in Feldmitte", L=2 * a, lager=fl(2 * a),
           lasten=[Strecke(0, a, 0, q0), Strecke(a, 2 * a, q0, 0)]),
    balken("EF09", "Einfeldträger, Trapezlast", L=l, lager=fl(l), lasten=[Strecke(0, l, q1, q2)],
           hinweis=r"Trapezlast als Überlagerung einer Rechtecklast \(q_1\) und einer Dreieckslast "
                   r"\(q_2 - q_1\) betrachten: Auflagerreaktionen und Verläufe beider Anteile addieren."),
    balken("EF10", "Einfeldträger, Einzelmoment am linken Lager", L=l, lager=fl(l), lasten=[Moment(0, M0)]),
    balken("EF11", "Einfeldträger, Einzelmoment in Feldmitte", L=l, lager=fl(l), lasten=[Moment(l / 2, M0)]),
    balken("EF12", "Einfeldträger, Einzelmoment außermittig", L=3 * a, lager=fl(3 * a),
           lasten=[Moment(a, M0, dreh="rechts")]),
    balken("EF13", "Einfeldträger, schräge Einzelkraft", L=l, lager=fl(l),
           lasten=[Kraft(l / 2, F, richtung=-45)]),
    balken("EF14", "Einfeldträger, Horizontalkraft", L=2 * a, lager=fl(2 * a),
           lasten=[Kraft(a, F, richtung="rechts")]),
    balken("EF15", "Einfeldträger, Horizontalkraft, Festlager rechts", L=2 * a,
           lager={0: Los(), 2 * a: Fest()}, lasten=[Kraft(a, F, richtung="rechts")]),
    balken("EF16", "Einfeldträger, Streckenlast und Einzelkraft", L=2 * a, lager=fl(2 * a),
           lasten=[Strecke(0, 2 * a, q), Kraft(a, F)]),
]
