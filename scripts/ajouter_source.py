#!/usr/bin/env python3
"""Ajoute une source à la veille à partir de sa seule adresse.

    python scripts/ajouter_source.py https://www.exemple.fr/actualites/

Sans option, le script enquête et affiche ce qu'il ferait : flux trouvé ou
méthode d'extraction, aperçu des articles, réserves éventuelles, et le bloc de
configuration proposé. Rien n'est écrit. Dans un terminal, il demande le nom et
le domaine s'ils ne sont pas donnés.

    --nom "…"       nom complet (proposé d'après la page à défaut)
    --court "…"     nom court affiché (le nom complet à défaut)
    --theme "…"     domaine, parmi ceux de settings.themes
    --ecrire        ajoute la source à config/sites.yml
    --forcer        écrit malgré un verdict « manuel » ou une adresse déjà suivie
    --json          sortie JSON pour un traitement automatique (aucune question)

Après --ecrire : `python generate.py` pour voir la source dans le tableau de
bord, puis committer config/sites.yml. Le push suffit à publier.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veille.config import load_config  # noqa: E402
from veille.fetch import request_session  # noqa: E402
from veille.onboarding import (  # noqa: E402
    VERDICT_MANUEL,
    VERDICT_OK,
    Proposal,
    append_site,
    investigate,
    render_block,
)

LIBELLES = {
    VERDICT_OK: "prête à être ajoutée",
    "a_verifier": "exploitable, mais à vérifier",
    VERDICT_MANUEL: "demande un réglage manuel",
}


def demander(question: str, defaut: str = "") -> str:
    """Pose une question ; garde la valeur par défaut si l'entrée est fermée."""
    try:
        reponse = input(f"{question}{f' [{defaut}]' if defaut else ''} : ").strip()
    except EOFError:
        print()
        return defaut
    return reponse or defaut


def choisir_theme(themes: list[str], actuel: str) -> str:
    if actuel or not themes:
        return actuel
    print("\nDomaine :")
    for n, t in enumerate(themes, 1):
        print(f"  {n}. {t}")
    for _ in range(3):
        saisie = demander("Numéro du domaine")
        if not saisie:
            return actuel
        if saisie.isdigit() and 1 <= int(saisie) <= len(themes):
            return themes[int(saisie) - 1]
        print("  Numéro invalide.")
    return actuel


def afficher(p: Proposal) -> None:
    print(f"\nSource : {p.name}" + (f"  (affichée « {p.short_name} »)" if p.short_name != p.name else ""))
    print(f"Domaine : {p.theme or '(non renseigné → « Autres »)'}")
    print(f"Collecte : {p.method}" + (f" — {p.official_feed}" if p.official_feed else ""))
    print(f"Verdict : {LIBELLES.get(p.verdict, p.verdict)}")
    for r in p.warnings:
        print(f"  ! {r}")
    if p.items:
        print(f"\nAperçu ({len(p.items)} premiers articles) :")
        for i in p.items:
            print(f"  {(i.published or 'sans date')[:10]}  {i.title[:80]}")
    print("\nBloc de configuration :\n" + render_block(p.to_site()))


def en_json(p: Proposal) -> str:
    donnees = asdict(p)
    donnees["items"] = [{"title": i.title, "link": i.link, "published": i.published} for i in p.items]
    donnees["block"] = render_block(p.to_site())
    donnees["verdict_label"] = LIBELLES.get(p.verdict, p.verdict)
    return json.dumps(donnees, ensure_ascii=False, indent=2)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--nom", default="")
    ap.add_argument("--court", default="")
    ap.add_argument("--theme", default="")
    ap.add_argument("--ecrire", action="store_true")
    ap.add_argument("--forcer", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config()
    settings = cfg.get("settings") or {}
    themes = [str(t) for t in (settings.get("themes") or [])]
    session = request_session(settings)
    interactif = sys.stdin.isatty() and not args.json

    try:
        proposition = investigate(
            session, args.url, name=args.nom, short_name=args.court, theme=args.theme,
            timeout=int(settings.get("request_timeout", 30)),
            max_items=int(settings.get("max_items_per_feed", 60)), cfg=cfg,
        )
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"Impossible d'enquêter sur {args.url} : {exc}")
        return 2

    if interactif:
        if not args.nom:
            proposition.name = demander("Nom de la source", proposition.name)
            for item in proposition.items:
                item.source = proposition.name
        if not args.court:
            proposition.short_name = demander("Nom court affiché", proposition.name)
        proposition.theme = choisir_theme(themes, proposition.theme)

    if args.json:
        print(en_json(proposition))
    else:
        afficher(proposition)

    if not args.ecrire:
        if not args.json:
            print("Rien n'a été écrit. Relancer avec --ecrire pour ajouter la source.")
        return 0 if proposition.verdict != VERDICT_MANUEL else 1

    bloquant = proposition.verdict == VERDICT_MANUEL or any("déjà suivie" in w for w in proposition.warnings)
    if bloquant and not args.forcer:
        print("Ajout refusé : verdict « manuel » ou adresse déjà suivie. Utiliser --forcer pour passer outre.")
        return 1
    append_site(proposition.to_site())
    print(f"Source ajoutée à config/sites.yml. Prochaine étape : python generate.py, puis committer.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
