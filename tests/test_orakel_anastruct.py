"""Unabhängige Gegenrechnung jedes Katalogsystems mit anaStruct (2D-FEM, numerisch).

Kalibrierung der Vorzeichen (siehe anastruct_bridge.py): Einfeldträger unter q (EF04),
Kragarm (KA01), Einzelmoment (EF11), Faser oben (VA01) und Winkelträger (WT01).
Statisch bestimmte Systeme sind unabhängig von EA/EI, daher muss FEM exakt dasselbe liefern.
"""

import warnings

import pytest

from anastruct_bridge import Unsupported, compare
from tm_anki.katalog import alle_systeme
from tm_anki.solver import solve

SYSTEME = alle_systeme()


@pytest.mark.parametrize("sysdef", SYSTEME, ids=[s.id for s in SYSTEME])
def test_katalog_gegen_anastruct(sysdef):
    result = solve(sysdef.structure)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            problems = compare(sysdef.structure, result)
        except Unsupported as exc:
            pytest.skip(f"von der Brücke nicht unterstützt: {exc}")
    assert not problems, "\n".join(problems)
