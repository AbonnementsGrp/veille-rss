#!/usr/bin/env python3
"""Traite une demande de suppression de source déposée par formulaire d'issue.

    python scripts/issue_supprimer_source.py enquete     # vérifie, écrit commentaire.md
    python scripts/issue_supprimer_source.py appliquer   # supprime, écrit commentaire.md

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
from veille.sources import RemovalPlan, apply_removal, plan_removal  # noqa: E402

# Libellés du formulaire .github/ISSUE_TEMPLATE/supprimer-source.yml → clé.
CHAMPS = {
    "Source à supprimer": "source",
    "Pourquoi la supprimer ?": "pourquoi",
}


def commentaire(plan: RemovalPlan, applique: bool = False) -> str:
    lignes = ["### " + ("✅ Source supprimée" if applique else "⚠️ Suppression prête à être appliquée"), ""]
    lignes.append(f"**Source reconnue** : {plan.name}"
                  + (f" (affichée « {plan.short_name} »)" if plan.short_name != plan.name else ""))
    lignes.append(f"**Domaine** : {plan.theme}")
    lignes.append(f"**Page** : {plan.url}")
    lignes.append(f"**Flux publié** : `{plan.output}`" + ("" if plan.feed_exists else " (déjà absent)"))
    lignes.append(f"**Historique** : {plan.history_entries} article(s)")
    lignes.append("")
    if applique:
        lignes.append("La configuration, l'historique et le flux publié ont été retirés. La source "
                      "disparaît du tableau de bord et de l'OPML à la prochaine génération.")
    else:
        lignes.append("**Cette opération est irréversible** : le flux publié et l'historique de la source "
                      "seront effacés. Vérifiez que la source reconnue ci-dessus est bien celle visée.")
        lignes.append("")
        lignes.append(APPROBATION)
    return "\n".join(lignes) + "\n"


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "enquete"
    champs = parse_form(os.environ.get("ISSUE_BODY", ""), CHAMPS)
    cfg = load_config()
    try:
        plan = plan_removal(champs.get("source", ""), cfg)
    except ValueError as exc:
        return refus(str(exc))

    if mode != "enquete":
        try:
            apply_removal(plan, history_limit=int((cfg.get("settings") or {}).get("max_history_items", 1000)))
        except ValueError as exc:
            write_outputs(f"❌ Suppression impossible : {exc}.\n", "erreur")
            return 1
        write_outputs(commentaire(plan, applique=True), "applique")
        return 0

    write_outputs(commentaire(plan), "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
