"""Surveillance de la qualité : repérer une source qui se dégrade en silence.

Une source peut rester « OK » tout en ne valant plus rien : le site a cessé de
publier, un sélecteur cassé ne ramène plus que le menu, les dates ont disparu
ou tombent dans le futur. Rien de tout cela ne lève d'erreur. Ce module rend,
pour chaque source, des avertissements en clair, repris dans status.json et au
tableau de bord. Un avertissement ne change pas l'état de la source : elle
reste publiée, mais quelqu'un doit aller voir.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from veille.dates import parse_date_for_feed
from veille.extract import PAGINATION_PATH, TAXONOMY_PATHS
from veille.models import Item

# Sans nouvel article au-delà de ce délai, la source est signalée. Réglable dans
# settings.stale_after_days ; une source à la cadence plus lente porte le sien.
STALE_AFTER_DAYS = 60
# Part des articles frais d'allure douteuse à partir de laquelle on s'alarme, et
# nombre minimal d'articles pour que la proportion ait un sens.
SUSPECT_RATIO = 0.3
MIN_ITEMS_FOR_CONTENT_CHECKS = 3
# En deçà, un titre est un libellé de menu plutôt qu'un titre d'article.
SHORT_TITLE = 10
# Une date à peine dans le futur tient au fuseau horaire ou à une publication
# programmée du jour ; au-delà, c'est une date mal lue.
FUTURE_TOLERANCE = timedelta(days=1)

# Libellés de navigation, tels qu'ils apparaissent quand un sélecteur cassé ne
# ramène plus que le menu ou le pied de page.
NAV_TITLES = frozenset({
    "accueil", "contact", "nous contacter", "actualités", "actualites", "actus", "agenda",
    "recherche", "rechercher", "connexion", "se connecter", "s'inscrire", "newsletter",
    "suivant", "précédent", "precedent", "menu", "partager", "imprimer", "retour",
    "haut de page", "cookies", "faq", "à propos", "a propos", "qui sommes-nous",
    "publications", "documentation", "espace presse", "presse", "recrutement", "emploi",
    "plan du site", "mentions légales", "politique de confidentialité", "flux rss",
    "english", "français", "page suivante", "page précédente",
})
# Un titre qui commence ainsi est un appel à cliquer, pas un titre.
NAV_PREFIXES = ("en savoir plus", "lire la suite", "lire l'article", "voir tout", "voir toutes",
                "toutes les actualités", "tous les articles")

# Méthodes qui livrent le contenu tel que le site le publie : y chercher des
# liens de navigation n'aurait pas de sens.
CONTENT_AS_PUBLISHED = ("flux officiel", "flux détecté", "plan de site")


def normalize_title(titre: str) -> str:
    return " ".join(titre.lower().replace("’", "'").split()).strip(" .:…»«")


def looks_like_navigation(item: Item, site_url: str = "") -> bool:
    """Dit si un article extrait ressemble à un lien de menu, de pagination ou de rubrique."""
    titre = normalize_title(item.title)
    if titre in NAV_TITLES or titre.startswith(NAV_PREFIXES):
        return True
    if len(titre) < SHORT_TITLE and not any(c.isdigit() for c in titre):
        return True
    lien = item.link.lower()
    if any(t in lien for t in TAXONOMY_PATHS) or PAGINATION_PATH.search(lien):
        return True
    return bool(site_url) and lien.rstrip("/") == site_url.lower().rstrip("/")


def days_since_last(items: list[Item], now: datetime) -> int | None:
    """Jours écoulés depuis l'article le plus récent (publication, sinon découverte) ; None sans date."""
    dates = [parse_date_for_feed(i.published or i.first_seen) for i in items if i.published or i.first_seen]
    dates = [d for d in dates if d]
    if not dates:
        return None
    return max(0, (now - max(dates)).days)


def content_as_published(method: str) -> bool:
    return method.startswith(CONTENT_AS_PUBLISHED)


def stale_threshold(site: dict[str, Any], settings: dict[str, Any]) -> int:
    return int(site.get("stale_after_days") or settings.get("stale_after_days") or STALE_AFTER_DAYS)


def quality_warnings(fresh: list[Item], published: list[Item], site: dict[str, Any],
                     settings: dict[str, Any], method: str, now: datetime) -> list[str]:
    """Les avertissements d'une source, en clair ; liste vide quand tout va bien.

    `fresh` : les articles collectés à cette exécution ; `published` : ceux du
    flux produit, historique compris. Le silence se juge sur les seconds, la
    forme du contenu sur les premiers.
    """
    avertissements: list[str] = []
    seuil = stale_threshold(site, settings)
    silence = days_since_last(published, now)
    if silence is not None and silence > seuil:
        avertissements.append(f"rien de neuf depuis {silence} jours (seuil : {seuil})")

    futurs = 0
    for item in fresh:
        date = parse_date_for_feed(item.published) if item.published else None
        if date and date > now + FUTURE_TOLERANCE:
            futurs += 1
    if futurs:
        avertissements.append(f"{futurs} article(s) daté(s) dans le futur")

    if len(fresh) >= MIN_ITEMS_FOR_CONTENT_CHECKS and not content_as_published(method):
        suspects = sum(1 for i in fresh if looks_like_navigation(i, str(site.get("url") or "")))
        if suspects / len(fresh) >= SUSPECT_RATIO:
            avertissements.append(f"{suspects} titre(s) sur {len(fresh)} ressemblent à des liens de navigation")
        if not any(i.published for i in fresh):
            avertissements.append("aucun article daté : ils sont datés du jour de leur découverte")
    return avertissements
