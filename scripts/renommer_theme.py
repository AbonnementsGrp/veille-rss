#!/usr/bin/env python3
"""Renomme un domaine (rubrique du tableau de bord).

    python scripts/renommer_theme.py "Culture" "Arts & Culture"
    python scripts/renommer_theme.py "Culture" "Arts & Culture" --ecrire

L'ancien nom est reconnu sans égard à la casse ni aux accents. Sans --ecrire,
affiche ce qui changerait et n'écrit rien. Avec, renomme le domaine partout :
liste des domaines, `theme` de chaque source concernée, liste déroulante du
formulaire de proposition de source. Les deux fichiers sont ensuite à committer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.config import load_config  # noqa: E402
from veille.themes import plan_rename, rename_theme  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ancien")
    ap.add_argument("nouveau")
    ap.add_argument("--ecrire", action="store_true")
    args = ap.parse_args(argv)

    try:
        plan = plan_rename(args.ancien, args.nouveau)
    except ValueError as exc:
        print(f"Refusé : {exc}")
        return 1

    concernees = [s for s in load_config()["sites"] if s.get("theme") == plan.old]
    print(f"« {plan.old} » devient « {plan.new} » ; {len(concernees)} source(s) concernée(s) :")
    for s in concernees:
        print(f"  - {s.get('short_name') or s['name']}")
    print("\nDomaines après renommage, par ordre alphabétique :")
    for n, theme in enumerate(plan.result, 1):
        print(f"  {n}. {theme}" + ("   <- renommé" if theme == plan.new else ""))
    if not args.ecrire:
        print("\nRien n'a été écrit. Relancer avec --ecrire pour appliquer.")
        return 0
    try:
        n = rename_theme(plan)
    except ValueError as exc:
        print(f"Renommage impossible : {exc}")
        return 1
    print(f"\nDomaine renommé, {n} source(s) rattachée(s) au nouveau nom. "
          "Committer config/sites.yml et .github/ISSUE_TEMPLATE/nouvelle-source.yml.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
