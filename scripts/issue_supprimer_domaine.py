#!/usr/bin/env python3
"""Traite une demande de suppression de domaine déposée par formulaire d'issue.

    python scripts/issue_supprimer_domaine.py enquete     # vérifie, écrit commentaire.md
    python scripts/issue_supprimer_domaine.py appliquer   # supprime, écrit commentaire.md

Le corps de l'issue est lu dans la variable d'environnement ISSUE_BODY.
Sorties : commentaire.md et verdict.txt (ok | erreur | applique).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.issues import APPROBATION, parse_form, refus, write_outputs  # noqa: E402
from veille.themes import ThemeRemovalPlan, plan_theme_removal, remove_theme  # noqa: E402

# Libellés du formulaire .github/ISSUE_TEMPLATE/supprimer-domaine.yml → clé.
CHAMPS = {
    "Domaine à supprimer": "domaine",
    "Rattacher ses sources à": "cible",
    "Pourquoi le supprimer ?": "pourquoi",
}


def destination(plan: ThemeRemovalPlan) -> str:
    if plan.target:
        return f"rattachées au domaine **« {plan.target} »**"
    return "désormais **sans domaine**, regroupées sous « Autres »"


def commentaire(plan: ThemeRemovalPlan, applique: bool = False) -> str:
    lignes = ["### " + ("✅ Domaine supprimé" if applique else "⚠️ Suppression prête à être appliquée"), ""]
    lignes.append(f"**Domaine reconnu** : {plan.name}")
    if plan.sources:
        lignes.append(f"**Sources concernées** : {len(plan.sources)} — {', '.join(plan.sources)} — {destination(plan)}")
    else:
        lignes.append("**Sources concernées** : aucune")
    lignes += ["", "**Domaines qui restent :**", ""]
    for n, theme in enumerate(plan.result, 1):
        lignes.append(f"{n}. {theme}")
    lignes.append("")
    if applique:
        lignes.append("Le domaine a disparu de la liste des domaines et du formulaire de proposition de "
                      "source ; le tableau de bord et l'OPML suivent à la prochaine génération. Aucune "
                      "source ni aucun article n'a été supprimé.")
    else:
        lignes.append("Aucune source ni aucun article ne sera supprimé : seules la rubrique et son entrée "
                      "dans le formulaire disparaissent. Vérifiez que le domaine reconnu est bien celui visé.")
        lignes.append("")
        lignes.append(APPROBATION)
    return "\n".join(lignes) + "\n"


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "enquete"
    champs = parse_form(os.environ.get("ISSUE_BODY", ""), CHAMPS)
    try:
        plan = plan_theme_removal(champs.get("domaine", ""), champs.get("cible", ""))
    except ValueError as exc:
        return refus(str(exc))

    if mode != "enquete":
        try:
            remove_theme(plan)
        except ValueError as exc:
            write_outputs(f"❌ Suppression impossible : {exc}.\n", "erreur")
            return 1
        write_outputs(commentaire(plan, applique=True), "applique")
        return 0

    write_outputs(commentaire(plan), "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
