#!/usr/bin/env python3
"""Supprime une source de la veille.

    python scripts/supprimer_source.py "IGAS"
    python scripts/supprimer_source.py "IGAS" --ecrire

La source est reconnue par son nom complet ou son nom court, sans égard à la
casse ni aux accents. Sans --ecrire, affiche ce qui serait retiré et n'écrit
rien. Avec, retire le bloc de config/sites.yml, purge l'historique de la source
et efface son flux publié dans public/. Committer ensuite ces trois éléments ;
la génération suivante ne la connaîtra plus.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.config import load_config  # noqa: E402
from veille.sources import apply_removal, plan_removal  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--ecrire", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config()
    try:
        plan = plan_removal(args.source, cfg)
    except ValueError as exc:
        print(f"Refusé : {exc}")
        return 1

    print(f"Source reconnue : {plan.name}" + (f" (affichée « {plan.short_name} »)" if plan.short_name != plan.name else ""))
    print(f"  domaine    : {plan.theme}")
    print(f"  page       : {plan.url}")
    print(f"  flux       : {plan.output}" + ("" if plan.feed_exists else " (absent du dossier publié)"))
    print(f"  historique : {plan.history_entries} article(s) à purger")
    if not args.ecrire:
        print("\nRien n'a été écrit. Relancer avec --ecrire pour supprimer.")
        return 0
    try:
        apply_removal(plan, history_limit=int((cfg.get("settings") or {}).get("max_history_items", 1000)))
    except ValueError as exc:
        print(f"Suppression impossible : {exc}")
        return 1
    print("\nSource supprimée. Committer config/sites.yml, data/history.json et public/.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
