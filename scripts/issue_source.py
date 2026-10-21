#!/usr/bin/env python3
"""Traite une demande de nouvelle source déposée par formulaire d'issue GitHub.

    python scripts/issue_source.py enquete    # enquête, écrit commentaire.md
    python scripts/issue_source.py ajouter    # ajoute à sites.yml, écrit commentaire.md

Le corps de l'issue est lu dans la variable d'environnement ISSUE_BODY, jamais
passé en argument de ligne de commande : il est écrit par le demandeur et ne
doit pas transiter par un shell.

Sorties, dans le dossier courant :
  commentaire.md   texte à publier en commentaire de l'issue
  verdict.txt      ok | a_verifier | manuel | erreur   (pour étiqueter l'issue)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.browser import BrowserSession  # noqa: E402
from veille.config import load_config  # noqa: E402
from veille.fetch import request_session  # noqa: E402
from veille.issues import avec_pied_de_page  # noqa: E402
from veille.onboarding import (  # noqa: E402
    VERDICT_MANUEL,
    VERDICT_OK,
    Proposal,
    append_site,
    investigate,
    render_block,
)
from veille.text import clean_text  # noqa: E402

# Libellés du formulaire .github/ISSUE_TEMPLATE/nouvelle-source.yml → clé.
CHAMPS = {
    "Adresse de la page d'actualités": "url",
    "Domaine": "domaine",
    "Nom de la source": "nom",
    "Nom court": "court",
    "Pourquoi cette source ?": "pourquoi",
}
VIDE = "_No response_"
TITRES = {
    VERDICT_OK: "✅ Source prête à être ajoutée",
    "a_verifier": "⚠️ Source exploitable, à vérifier avant d'approuver",
    VERDICT_MANUEL: "❌ Cette source demande un réglage manuel",
}
# Codes par lesquels un site refuse une page à un robot : accès interdit, trop de
# requêtes, ou service « indisponible » d'une page de vérification anti-robots.
# adaptation-changement-climatique.gouv.fr répond ainsi, par une « Vérification
# du navigateur » en 503, à tout client qui n'exécute pas son JavaScript.
CODES_REFUS = {403, 429, 503}


def parse_issue_body(body: str) -> dict[str, str]:
    """Lit les champs d'un formulaire d'issue : `### Libellé` suivi de la valeur."""
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


def commentaire(p: Proposal, ajoutee: bool = False) -> str:
    lignes = [f"### {TITRES.get(p.verdict, p.verdict)}", ""]
    lignes.append(f"**Source** : {p.name}" + (f" (affichée « {p.short_name} »)" if p.short_name != p.name else ""))
    lignes.append(f"**Domaine** : {p.theme or '_non renseigné_'}")
    lignes.append(f"**Collecte** : {p.method}" + (f" — `{p.official_feed}`" if p.official_feed else ""))
    if p.warnings:
        lignes += ["", "**Réserves :**"] + [f"- {w}" for w in p.warnings]
    if p.items:
        lignes += ["", f"**Aperçu ({len(p.items)} premiers articles) :**", "", "| Date | Titre |", "|---|---|"]
        for i in p.items:
            titre = i.title.replace("|", "\\|")[:90]
            lignes.append(f"| {(i.published or '—')[:10]} | [{titre}]({i.link}) |")
    lignes += ["", "**Configuration proposée :**", "", "```yaml", render_block(p.to_site()).rstrip(), "```", ""]
    if ajoutee:
        lignes += ["✅ **Source ajoutée.** Elle apparaîtra sur le tableau de bord à la prochaine "
                   "génération, sous quelques minutes."]
    elif p.verdict == VERDICT_MANUEL:
        lignes += ["Cette page ne se laisse pas lire automatiquement — site en JavaScript ou structure "
                   "inhabituelle. Un responsable devra écrire la configuration à la main, ou une autre "
                   "page du site (sa rubrique actualités) peut être proposée."]
    else:
        lignes += ["Pour ajouter la source, un responsable pose l'étiquette **approuvé** sur cette issue. "
                   "Pour ajuster le nom ou le domaine, modifiez le formulaire ci-dessus : l'enquête "
                   "sera relancée."]
    return "\n".join(lignes) + "\n"


def echec_enquete(url: str, exc: Exception) -> str:
    """Le commentaire d'une enquête impossible, avec ce que le demandeur peut y faire.

    Une page refusée au robot ne se débloque pas en revérifiant son adresse : le
    commentaire le dit et oriente vers le flux RSS du site. La veille ne contourne
    pas ces protections.
    """
    reponse = getattr(exc, "response", None)
    code = getattr(reponse, "status_code", None)
    if code not in CODES_REFUS:
        return (f"❌ Impossible d'enquêter sur `{url}` : {exc}\n\n"
                "Vérifiez l'adresse, puis modifiez l'issue pour relancer.\n")
    soup = BeautifulSoup(reponse.text, "html.parser")
    titre = clean_text(soup.title.get_text(), 120) if soup.title else ""
    return (
        f"❌ Le site refuse cette page au robot de la veille (code {code}"
        + (f", page « {titre} »" if titre else "") + ").\n\n"
        f"Si `{url}` s'ouvre normalement dans votre navigateur, le site la protège contre les "
        "robots : relancer l'enquête n'y changera rien, et la veille ne contourne pas ces "
        "protections. Si elle ne s'ouvre pas non plus, le site est momentanément indisponible : "
        "réessayez plus tard en modifiant l'issue.\n\n"
        "Proposez plutôt le **flux RSS** du site, s'il en publie un : cherchez un lien « Flux RSS » "
        "ou « RSS », souvent en haut ou en pied de page, et mettez son adresse à la place de "
        "celle-ci en modifiant l'issue. Une autre page du site qui liste les mêmes articles peut "
        "aussi convenir.\n"
    )


def ecrire(nom: str, contenu: str) -> None:
    if nom == "commentaire.md":
        contenu = avec_pied_de_page(contenu)
    Path(nom).write_text(contenu, encoding="utf-8")


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "enquete"
    champs = parse_issue_body(os.environ.get("ISSUE_BODY", ""))
    url = champs.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        ecrire("commentaire.md", "❌ Aucune adresse valide trouvée dans le formulaire. "
               "Modifiez l'issue en indiquant l'adresse complète, commençant par `https://`.\n")
        ecrire("verdict.txt", "erreur")
        return 1

    cfg = load_config()
    settings = cfg.get("settings") or {}
    try:
        # Le navigateur n'est lancé que si la page ne livre rien à la session
        # HTTP ; il permet de proposer `render: true` pour un site en JavaScript.
        with BrowserSession(user_agent=str(settings.get("user_agent", ""))) as navigateur:
            p = investigate(
                request_session(settings), url,
                name=champs.get("nom", ""), short_name=champs.get("court", ""), theme=champs.get("domaine", ""),
                timeout=int(settings.get("request_timeout", 30)),
                max_items=int(settings.get("max_items_per_feed", 60)), cfg=cfg, browser=navigateur,
            )
    except Exception as exc:
        ecrire("commentaire.md", echec_enquete(url, exc))
        ecrire("verdict.txt", "erreur")
        return 1

    if mode == "ajouter":
        bloquant = p.verdict == VERDICT_MANUEL or any("déjà suivie" in w for w in p.warnings)
        if bloquant:
            ecrire("commentaire.md", "❌ Ajout refusé : " + (
                "la source demande un réglage manuel." if p.verdict == VERDICT_MANUEL
                else "cette adresse est déjà suivie.") + "\n\n" + commentaire(p))
            ecrire("verdict.txt", p.verdict)
            return 1
        append_site(p.to_site())
        ecrire("commentaire.md", commentaire(p, ajoutee=True))
        ecrire("verdict.txt", "ajoutee")
        return 0

    ecrire("commentaire.md", commentaire(p))
    ecrire("verdict.txt", p.verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
