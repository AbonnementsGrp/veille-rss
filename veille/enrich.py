"""Résumé d'un article lu sur sa propre page.

Certains flux WordPress ne publient aucun résumé : leur `<description>` ne
contient que la mention « L'article … est apparu en premier sur … », et le
`content:encoded` répète la même chose. Le seul endroit où trouver un résumé
est alors la page de l'article.

Chaque article n'est visité qu'une fois : l'historique garde la trace de la
tentative, réussie ou non, afin de ne pas redemander la même page toutes les
trois heures.
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from veille.text import clean_summary, clean_text

log = logging.getLogger(__name__)

# Métadonnées de partage, dans l'ordre de fiabilité.
META_SELECTORS = (
    'meta[property="og:description"]',
    'meta[name="description"]',
    'meta[name="twitter:description"]',
)
# Le titre ne vient que des métadonnées de partage, jamais de <title> : sur un
# site rendu en JavaScript, <title> porte souvent le nom du site, pas celui de
# l'article, alors que les métadonnées de partage ne sont posées que pour lui.
TITLE_SELECTORS = (
    'meta[property="og:title"]',
    'meta[name="twitter:title"]',
)
MIN_TITLE_LENGTH = 8
MAX_TITLE_LENGTH = 200
# Un titre de partage au moins aussi long, sans ponctuation finale, a pu être
# coupé par le site (Salesforce tronque og:title à soixante caractères).
TRUNCATION_SUSPECT_LENGTH = 50
TERMINAL_PUNCTUATION = ".!?»\")"
# Éléments où chercher le titre entier d'une page : les titres, et tout ce que
# le site nomme lui-même « title » ou « titre ».
TITLE_ELEMENTS = "h1, h2, h3, [class*=title], [class*=titre]"
# En deçà, le texte est un fragment de navigation, pas un résumé.
MIN_SUMMARY_LENGTH = 60
SUMMARY_LIMIT = 500
# Au-delà de cette proportion de mots capitalisés, le texte est une liste de
# noms propres et non une phrase. Les pages de rapports de l'Igas mettent ainsi
# la liste de leurs auteurs en og:description et en premier paragraphe.
MAX_CAPITALIZED_RATIO = 0.6
MIN_WORDS = 6


def looks_like_summary(texte: str) -> bool:
    """Dit si un texte peut servir de résumé, ou n'est qu'une liste de noms."""
    if len(texte) < MIN_SUMMARY_LENGTH:
        return False
    mots = [m for m in texte.split() if any(c.isalpha() for c in m)]
    if len(mots) < MIN_WORDS:
        return False
    capitalises = sum(1 for m in mots if m[:1].isupper())
    return capitalises / len(mots) <= MAX_CAPITALIZED_RATIO


def looks_like_title(texte: str) -> bool:
    """Un titre d'article : assez long, et pas un sigle ou un cri en capitales."""
    return len(texte) >= MIN_TITLE_LENGTH and any(c.islower() for c in texte)


def looks_truncated(titre: str) -> bool:
    return len(titre) >= TRUNCATION_SUSPECT_LENGTH and titre[-1] not in TERMINAL_PUNCTUATION


def complete_title(soup: BeautifulSoup, titre: str) -> str:
    """Rend le titre entier quand les métadonnées de partage l'ont coupé.

    L'en-tête de l'article porte le titre complet : l'élément le plus court
    dont le texte commence par le titre coupé et le prolonge est retenu. Le plus
    court, pour ne pas prendre un bloc qui enchaîne titre et date.
    """
    amorce = titre.rstrip(" .…")
    if not looks_truncated(titre) or len(amorce) < MIN_TITLE_LENGTH:
        return titre
    candidats = []
    for element in soup.select(TITLE_ELEMENTS):
        texte = clean_text(element.get_text(" ", strip=True))
        if texte.startswith(amorce) and len(titre) < len(texte) <= MAX_TITLE_LENGTH:
            candidats.append(texte)
    return min(candidats, key=len) if candidats else titre


def article_metadata(session: Any, url: str, timeout: int) -> tuple[str, str]:
    """Rend (titre, résumé) lus sur la page de l'article ; l'un ou l'autre peut être vide."""
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    titre = ""
    for selecteur in TITLE_SELECTORS:
        noeud = soup.select_one(selecteur)
        candidat = clean_text(str(noeud.get("content") or "")) if noeud else ""
        if looks_like_title(candidat):
            titre = complete_title(soup, candidat)
            break
    return titre, summary_from_page(soup)


def describe_article(session: Any, url: str, timeout: int) -> str:
    """Rend un résumé lu sur la page de l'article, ou "" si rien d'exploitable."""
    return article_metadata(session, url, timeout)[1]


def summary_from_page(soup: BeautifulSoup) -> str:
    for selecteur in META_SELECTORS:
        noeud = soup.select_one(selecteur)
        contenu = noeud.get("content") if noeud else ""
        texte = clean_summary(contenu, SUMMARY_LIMIT)
        if looks_like_summary(texte):
            return texte

    for balise in ("script", "style", "noscript", "svg", "nav", "header", "footer", "aside"):
        for node in soup.select(balise):
            node.decompose()
    for conteneur in ("article", "main", "body"):
        racine = soup.select_one(conteneur)
        if not racine:
            continue
        for paragraphe in racine.select("p"):
            texte = clean_summary(paragraphe.get_text(" ", strip=True), SUMMARY_LIMIT)
            if looks_like_summary(texte):
                return texte
        break
    return ""
