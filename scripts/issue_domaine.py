#!/usr/bin/env python3
"""Traite une demande de nouveau domaine déposée par formulaire d'issue GitHub.

    python scripts/issue_domaine.py enquete    # vérifie, écrit commentaire.md
    python scripts/issue_domaine.py ajouter    # écrit le domaine, écrit commentaire.md

Le corps de l'issue est lu dans la variable d'environnement ISSUE_BODY, jamais
passé en argument : il est écrit par le demandeur et ne doit pas transiter par
un shell.

Sorties, dans le dossier courant :
  commentaire.md   texte à publier en commentaire de l'issue
  verdict.txt      ok | erreur | ajoute
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.themes import ThemePlan, add_theme, plan_theme  # noqa: E402

# Libellés du formulaire .github/ISSUE_TEMPLATE/nouveau-domaine.yml → clé.
CHAMPS = {
    "Nom du domaine": "nom",
    "Pourquoi ce domaine ?": "pourquoi",
}
VIDE = "_No response_"


def parse_issue_body(body: str) -> dict[str, str]:
    champs: dict[str, str] = {}
    for bloc in re.split(r"^###\s+", body, flags=re.MULTILINE):
        if not bloc.strip():
            continue
        libelle, _, valeur = bloc.partition("\n")
        cle = CHAMPS.get(libelle.strip())
        if cle:
            valeur = valeur.strip()
            champs[cle] = "" if valeur == VIDE else valeur
    return champs


def commentaire(plan: ThemePlan, ajoute: bool = False) -> str:
    lignes = ["### ✅ " + ("Domaine ajouté" if ajoute else "Domaine prêt à être créé"), ""]
    lignes.append(f"**Nom** : {plan.name}")
    lignes.append(f"**Place** : {plan.position}ᵉ sur {len(plan.result)}, par ordre alphabétique")
    lignes += ["", "**Domaines qui en résultent :**", ""]
    for n, theme in enumerate(plan.result, 1):
        lignes.append(f"{n}. " + (f"**{theme}** ← nouveau" if theme == plan.name else theme))
    lignes.append("")
    if ajoute:
        lignes.append("Le domaine figure désormais dans la liste proposée au moment d'ajouter une source. "
                      "Il apparaîtra sur le tableau de bord dès qu'une source lui sera rattachée.")
    else:
        lignes.append("Pour créer le domaine, un responsable pose l'étiquette **approuvé** sur cette issue. "
                      "Pour changer le nom, modifiez le formulaire ci-dessus : la vérification sera relancée.")
    return "\n".join(lignes) + "\n"


def ecrire(nom: str, contenu: str) -> None:
    Path(nom).write_text(contenu, encoding="utf-8")


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "enquete"
    champs = parse_issue_body(os.environ.get("ISSUE_BODY", ""))
    try:
        plan = plan_theme(champs.get("nom", ""))
    except ValueError as exc:
        ecrire("commentaire.md", f"❌ Demande refusée : {exc}.\n\nModifiez le formulaire ci-dessus pour corriger.\n")
        ecrire("verdict.txt", "erreur")
        return 1

    if mode == "ajouter":
        try:
            add_theme(plan)
        except ValueError as exc:
            ecrire("commentaire.md", f"❌ Ajout impossible : {exc}.\n")
            ecrire("verdict.txt", "erreur")
            return 1
        ecrire("commentaire.md", commentaire(plan, ajoute=True))
        ecrire("verdict.txt", "ajoute")
        return 0

    ecrire("commentaire.md", commentaire(plan))
    ecrire("verdict.txt", "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
