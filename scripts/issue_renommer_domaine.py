#!/usr/bin/env python3
"""Traite une demande de renommage de domaine déposée par formulaire d'issue.

    python scripts/issue_renommer_domaine.py enquete     # vérifie, écrit commentaire.md
    python scripts/issue_renommer_domaine.py appliquer   # renomme, écrit commentaire.md

Le corps de l'issue est lu dans la variable d'environnement ISSUE_BODY.
Sorties : commentaire.md et verdict.txt (ok | erreur | applique).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.config import load_config  # noqa: E402
from veille.issues import APPROBATION, parse_form, refus, write_outputs  # noqa: E402
from veille.themes import RenamePlan, plan_rename, rename_theme  # noqa: E402

# Libellés du formulaire .github/ISSUE_TEMPLATE/renommer-domaine.yml → clé.
CHAMPS = {
    "Domaine actuel": "ancien",
    "Nouveau nom": "nouveau",
    "Pourquoi ce changement ?": "pourquoi",
}


def commentaire(plan: RenamePlan, concernees: list[str], applique: bool = False) -> str:
    lignes = ["### ✅ " + ("Domaine renommé" if applique else "Renommage prêt à être appliqué"), ""]
    lignes.append(f"**« {plan.old} »** devient **« {plan.new} »**")
    lignes.append(f"**Sources concernées** : {len(concernees)}" + (" — " + ", ".join(concernees) if concernees else ""))
    lignes += ["", "**Domaines qui en résultent :**", ""]
    for n, theme in enumerate(plan.result, 1):
        lignes.append(f"{n}. " + (f"**{theme}** ← renommé" if theme == plan.new else theme))
    lignes.append("")
    lignes.append("Le nouveau nom est en place sur le tableau de bord, dans l'OPML et dans le formulaire "
                  "de proposition de source ; il apparaîtra à la prochaine génération." if applique
                  else APPROBATION)
    return "\n".join(lignes) + "\n"


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "enquete"
    champs = parse_form(os.environ.get("ISSUE_BODY", ""), CHAMPS)
    try:
        plan = plan_rename(champs.get("ancien", ""), champs.get("nouveau", ""))
    except ValueError as exc:
        return refus(str(exc))
    concernees = [str(s.get("short_name") or s["name"]) for s in load_config()["sites"] if s.get("theme") == plan.old]

    if mode != "enquete":
        try:
            rename_theme(plan)
        except ValueError as exc:
            write_outputs(f"❌ Renommage impossible : {exc}.\n", "erreur")
            return 1
        write_outputs(commentaire(plan, concernees, applique=True), "applique")
        return 0

    write_outputs(commentaire(plan, concernees), "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
