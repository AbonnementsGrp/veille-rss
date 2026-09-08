"""Traitement commun des demandes déposées par formulaire d'issue GitHub.

Un formulaire d'issue arrive sous forme de Markdown : chaque champ est un titre
`### Libellé` suivi de sa valeur, ou de `_No response_` s'il est resté vide. Les
scripts `scripts/issue_*.py` lisent ce corps, produisent un commentaire et un
verdict que le workflow publie et étiquette.
"""

from __future__ import annotations

import re
from pathlib import Path

VIDE = "_No response_"

APPROBATION = ("Pour appliquer, un responsable pose l'étiquette **approuvé** sur cette issue. "
               "Pour corriger, modifiez le formulaire ci-dessus : la vérification sera relancée.")

# GitHub n'offre aucun bouton de retour depuis ses pages d'issues : chaque
# commentaire automatique se termine par le chemin du tableau de bord.
DASHBOARD_URL = "https://abonnementsgrp.github.io/veille-rss/"
PIED_DE_PAGE = f"\n---\n[← Retour au tableau de bord de la veille]({DASHBOARD_URL})\n"


def avec_pied_de_page(commentaire: str) -> str:
    """Le commentaire suivi du lien de retour, sans le doubler."""
    if PIED_DE_PAGE.strip() in commentaire:
        return commentaire
    return commentaire.rstrip("\n") + "\n" + PIED_DE_PAGE


def parse_form(body: str, champs: dict[str, str]) -> dict[str, str]:
    """Lit les champs d'un formulaire : `champs` associe chaque libellé à une clé."""
    resultat: dict[str, str] = {}
    for bloc in re.split(r"^###\s+", body or "", flags=re.MULTILINE):
        if not bloc.strip():
            continue
        libelle, _, valeur = bloc.partition("\n")
        cle = champs.get(libelle.strip())
        if cle:
            valeur = valeur.strip()
            resultat[cle] = "" if valeur == VIDE else valeur
    return resultat


def write_outputs(commentaire: str, verdict: str, dossier: Path | None = None) -> None:
    """Dépose commentaire.md et verdict.txt, que le workflow relit ensuite."""
    dossier = dossier or Path.cwd()
    (dossier / "commentaire.md").write_text(avec_pied_de_page(commentaire), encoding="utf-8")
    (dossier / "verdict.txt").write_text(verdict, encoding="utf-8")


def refus(raison: str, dossier: Path | None = None) -> int:
    """Commentaire et verdict d'une demande refusée ; rend le code de sortie."""
    write_outputs(f"❌ Demande refusée : {raison}.\n\nModifiez le formulaire ci-dessus pour corriger.\n",
                  "erreur", dossier)
    return 1
