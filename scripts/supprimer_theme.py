#!/usr/bin/env python3
"""Supprime un domaine (rubrique du tableau de bord) sans toucher à ses sources.

    python scripts/supprimer_theme.py "Tourisme"
    python scripts/supprimer_theme.py "Tourisme" --vers "Culture" --ecrire

Le domaine est reconnu sans égard à la casse ni aux accents. Sans --ecrire,
affiche ce qui changerait et n'écrit rien. Avec, retire le domaine de la liste
des domaines et de la liste déroulante du formulaire de proposition de source,
et rattache ses sources au domaine donné par --vers ; sans --vers, elles perdent
leur domaine et passent sous « Autres ». Les deux fichiers sont ensuite à
committer. Aucune source ni aucun article n'est supprimé.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.themes import plan_theme_removal, remove_theme  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("domaine")
    ap.add_argument("--vers", default="", help="domaine qui accueille les sources ; sinon « Autres »")
    ap.add_argument("--ecrire", action="store_true")
    args = ap.parse_args(argv)

    try:
        plan = plan_theme_removal(args.domaine, args.vers)
    except ValueError as exc:
        print(f"Refusé : {exc}")
        return 1

    destination = f"rattachées à « {plan.target} »" if plan.target else "sans domaine, sous « Autres »"
    print(f"« {plan.name} » disparaît ; {len(plan.sources)} source(s) concernée(s), {destination} :")
    for nom in plan.sources:
        print(f"  - {nom}")
    print("\nDomaines restants, par ordre alphabétique :")
    for n, theme in enumerate(plan.result, 1):
        print(f"  {n}. {theme}")
    if not args.ecrire:
        print("\nRien n'a été écrit. Relancer avec --ecrire pour appliquer.")
        return 0
    try:
        n = remove_theme(plan)
    except ValueError as exc:
        print(f"Suppression impossible : {exc}")
        return 1
    print(f"\nDomaine supprimé, {n} source(s) déplacée(s). "
          "Committer config/sites.yml et .github/ISSUE_TEMPLATE/nouvelle-source.yml.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
