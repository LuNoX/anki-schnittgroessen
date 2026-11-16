from ..dsl import M0, Einspannung, F, Fest, Kraft, Los, Moment, Strecke, a, balken, q

KATEGORIE = "Gerberträger"

EGL = {0: Einspannung(), 3 * a: Los()}  # Einspannung - Gelenk bei a - Loslager
FLGL = {0: Fest(), 2 * a: Los(), 5 * a: Los()}  # Fest - Los - Gelenk bei 3a - Los

SYSTEME = [
    balken("GT01", "Gerberträger, Einzelkraft im Einhängeträger", L=3 * a, lager=EGL, gelenke=[a],
           lasten=[Kraft(2 * a, F)]),
    balken("GT02", "Gerberträger, Gleichstreckenlast", L=3 * a, lager=EGL, gelenke=[a],
           lasten=[Strecke(0, 3 * a, q)]),
    balken("GT03", "Gerberträger, Einzelmoment im Einhängeträger", L=3 * a, lager=EGL, gelenke=[a],
           lasten=[Moment(2 * a, M0)]),
    balken("GT04", "Gerberträger, Einzelkraft im Gelenk", L=2 * a, lager={0: Einspannung(), 2 * a: Los()},
           gelenke=[a], lasten=[Kraft(a, F)]),
    balken("GT05", "Gelenkträger mit Kragarm, Gleichstreckenlast", L=5 * a, lager=FLGL, gelenke=[3 * a],
           lasten=[Strecke(0, 5 * a, q)]),
    balken("GT06", "Gelenkträger mit Kragarm, Einzelkraft im Einhängeträger", L=5 * a, lager=FLGL,
           gelenke=[3 * a], lasten=[Kraft(4 * a, F)]),
]
