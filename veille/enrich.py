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

from veille.text import clean_summary

log = logging.getLogger(__name__)

# Métadonnées de partage, dans l'ordre de fiabilité.
META_SELECTORS = (
    'meta[property="og:description"]',
    'meta[name="description"]',
    'meta[name="twitter:description"]',
)
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


def describe_article(session: Any, url: str, timeout: int) -> str:
    """Rend un résumé lu sur la page de l'article, ou "" si rien d'exploitable."""
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

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
