"""Kommandozeile: ``uv run tm-anki check|build|list``."""

from __future__ import annotations

import argparse
import fnmatch
import io
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def _select(patterns: str | None):
    from .katalog import alle_systeme

    systeme = alle_systeme()
    if not patterns:
        return systeme
    pats = [p.strip() for p in patterns.split(",") if p.strip()]
    chosen = [s for s in systeme if any(fnmatch.fnmatchcase(s.id, p) for p in pats)]
    if not chosen:
        sys.exit(f"Keine Systeme passen zu {patterns!r}")
    return chosen


def _cards_for(sid: str, fmt: str, darstellung: str | None = None):
    from .deck import make_cards
    from .katalog import alle_systeme

    sysdef = next(s for s in alle_systeme() if s.id == sid)
    return make_cards(sysdef, fmt, darstellung)


def cmd_list(args) -> int:
    for s in _select(args.only):
        print(f"{s.id:6} {s.kategorie:22} {s.titel}")
    return 0


def cmd_check(args) -> int:
    from .checks import check
    from .solver import solve

    failed = 0
    for s in _select(args.only):
        try:
            result = solve(s.structure)
            errors, warnings = check(s, result)
        except Exception as exc:  # pylint: disable=broad-exception-caught  # jedes System melden, nicht abbrechen
            errors, warnings = [f"{type(exc).__name__}: {exc}"], []
        qtys = ",".join(s.groessen or (result.nonzero_quantities() if not errors else ()))
        status = "FEHLER" if errors else "ok"
        print(f"{s.id:6} {status:6} [{qtys}] {s.titel}")
        for w in warnings:
            print(f"         Warnung: {w}")
        for e in errors:
            print(f"         {e}")
        failed += bool(errors)
    print(f"\n{failed} System(e) mit Fehlern" if failed else "\nAlle Systeme ok")
    return 1 if failed else 0


def cmd_build(args) -> int:
    from .deck import write_package, write_preview

    systeme = _select(args.only)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    results: dict[str, list] = {}
    jobs = max(1, args.jobs)
    if jobs == 1:
        for s in systeme:
            results[s.id] = _cards_for(s.id, args.format, args.darstellung)
            print(f"  {s.id}: {len(results[s.id])} Karte(n)", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            futs = {ex.submit(_cards_for, s.id, args.format, args.darstellung): s.id for s in systeme}
            for fut in as_completed(futs):
                sid = futs[fut]
                results[sid] = fut.result()
                print(f"  {sid}: {len(results[sid])} Karte(n)", flush=True)
    cards = [c for s in systeme for c in results[s.id]]  # Katalogreihenfolge
    apkg = write_package(cards, out)
    print(f"\n{len(cards)} Karten aus {len(systeme)} Systemen in {time.time() - t0:.0f} s -> {apkg}")
    if args.preview:
        print(f"Vorschau: {write_preview(cards, out)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Umlaute auch in der Windows-Konsole
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="tm-anki", description="Anki-Karten für Schnittgrößenverläufe")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="Systeme auflisten")
    p_list.add_argument("--only", help="IDs/Muster, z. B. EF05,RA*")
    p_list.set_defaults(func=cmd_list)

    p_check = sub.add_parser("check", help="alle Systeme lösen und Invarianten prüfen")
    p_check.add_argument("--only", help="IDs/Muster, z. B. EF05,RA*")
    p_check.set_defaults(func=cmd_check)

    p_build = sub.add_parser("build", help="Deck (.apkg) bauen")
    p_build.add_argument("--only", help="IDs/Muster, z. B. EF05,RA*")
    p_build.add_argument("--format", choices=["svg", "png"], default="svg")
    p_build.add_argument(
        "--darstellung",
        choices=["auto", "im_system", "separat"],
        help="Verlauf im System oder separat zeichnen (Standard: Katalog bzw. conventions.py)",
    )
    p_build.add_argument("--preview", action="store_true", help="zusätzlich build/preview.html schreiben")
    p_build.add_argument("--out", default="build")
    p_build.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p_build.set_defaults(func=cmd_build)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
