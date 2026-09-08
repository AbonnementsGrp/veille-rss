#!/usr/bin/env python3
"""Ajoute un domaine (rubrique du tableau de bord) à la veille.

    python scripts/ajouter_theme.py "Logement & Habitat"
    python scripts/ajouter_theme.py "Logement & Habitat" --ecrire

Sans --ecrire, affiche la liste alphabétique des domaines qui en résulterait et
n'écrit rien. Avec, réécrit la liste aux deux endroits où elle vit :
`settings.themes` dans config/sites.yml et la liste déroulante du formulaire de
proposition de source. Les deux fichiers sont ensuite à committer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.themes import add_theme, plan_theme  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nom")
    ap.add_argument("--ecrire", action="store_true")
    args = ap.parse_args(argv)

    try:
        plan = plan_theme(args.nom)
    except ValueError as exc:
        print(f"Refusé : {exc}")
        return 1

    print("Domaines après ajout, par ordre alphabétique :")
    for n, theme in enumerate(plan.result, 1):
        print(f"  {n}. {theme}" + ("   <- nouveau" if theme == plan.name else ""))
    if not args.ecrire:
        print("\nRien n'a été écrit. Relancer avec --ecrire pour ajouter le domaine.")
        return 0
    try:
        add_theme(plan)
    except ValueError as exc:
        print(f"Ajout impossible : {exc}")
        return 1
    print("\nDomaine ajouté à config/sites.yml et au formulaire de proposition de source. "
          "Committer les deux fichiers.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
