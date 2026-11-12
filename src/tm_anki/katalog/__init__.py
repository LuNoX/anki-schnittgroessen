"""Systemkatalog.

Jedes Modul definiert ``KATEGORIE`` und eine Liste ``SYSTEME``. Die Reihenfolge der Module
und Einträge bestimmt die Reihenfolge der neuen Karten in Anki (einfach -> komplex).
Neues Modul? Einfach hier in ``MODULE`` eintragen.
"""

from __future__ import annotations

from importlib import import_module

from ..model import ModelError, SystemDef

MODULE = ["einfeld", "kragarm", "ueberstand", "gerber", "varianten", "schraeg", "winkel", "rahmen"]


def alle_systeme() -> list[SystemDef]:
    systeme: list[SystemDef] = []
    ids: set[str] = set()
    for name in MODULE:
        mod = import_module(f".{name}", __name__)
        for sysdef in mod.SYSTEME:
            if not sysdef.kategorie:
                sysdef.kategorie = mod.KATEGORIE
            if sysdef.id in ids:
                raise ModelError(f"ID {sysdef.id} ist doppelt vergeben")
            ids.add(sysdef.id)
            systeme.append(sysdef)
    return systeme
