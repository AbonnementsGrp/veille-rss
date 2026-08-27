#!/usr/bin/env python3
"""Retire de l'historique toutes les entrées d'une source.

L'historique complète chaque flux : les articles récoltés par une méthode
d'extraction que l'on vient d'abandonner continueraient donc d'être publiés.
Ce script permet de repartir proprement pour une source.

    python scripts/purger_source.py "ADN Tourisme"              # aperçu seul
    python scripts/purger_source.py "ADN Tourisme" --appliquer  # écrit
    python scripts/purger_source.py --lister                    # sources connues

Relancer ensuite `python generate.py` pour reconstituer le flux.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.config import HISTORY_PATH, load_config  # noqa: E402
from veille.history import load_history, remove_source, save_history  # noqa: E402


def lister(history: dict) -> int:
    compte = Counter(r.get("source", "?") for r in history.values())
    print(f"{len(history)} entrée(s) dans {HISTORY_PATH.name} :")
    for source, n in compte.most_common():
        print(f"  {n:4}  {source}")
    return 0


def main(argv: list[str]) -> int:
    arguments = [a for a in argv if not a.startswith("--")]
    options = {a for a in argv if a.startswith("--")}
    history = load_history()

    if "--lister" in options or not arguments:
        return lister(history)

    source = arguments[0]
    connues = {r.get("source") for r in history.values()}
    if source not in connues:
        print(f"Source inconnue : {source!r}")
        print("Utiliser --lister pour voir les sources présentes dans l'historique.")
        return 1

    vises = [r for r in history.values() if r.get("source") == source]
    print(f"{len(vises)} entrée(s) pour {source!r} :")
    for r in sorted(vises, key=lambda r: r.get("published") or "", reverse=True)[:10]:
        print(f"  {(r.get('published') or '?')[:10]}  {r.get('title', '')[:66]}")
    if len(vises) > 10:
        print(f"  … et {len(vises) - 10} autre(s)")

    if "--appliquer" not in options:
        print("\nAperçu seul. Ajouter --appliquer pour écrire la suppression.")
        return 0

    limite = int((load_config().get("settings") or {}).get("max_history_items", 1000))
    retirees = remove_source(history, source)
    save_history(history, limite)
    print(f"\n{retirees} entrée(s) retirée(s). Relancer generate.py pour reconstituer le flux.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
