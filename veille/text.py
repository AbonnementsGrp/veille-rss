"""Nettoyage des textes extraits des flux et des pages."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

# Reconnaît une balise HTML, pour distinguer du balisage d'un simple « < ».
HTML_TAG = re.compile(r"</?[a-z][a-z0-9]*(?:\s[^>]*)?/?>", re.IGNORECASE)
MAX_UNESCAPE_PASSES = 4

# Mention que WordPress ajoute au résumé de chaque article de son flux :
# « L'article <titre> est apparu en premier sur <site>. » Elle n'apporte rien
# et occupe souvent la place du résumé à elle seule.
BOILERPLATE = re.compile(
    r"\s*(?:L['’]article|The post)\s+.{0,400}?"
    r"\s+(?:est apparu en premier sur|appeared first on)\s+[^.]{0,120}\.?\s*",
    re.IGNORECASE | re.DOTALL,
)


def has_hidden_markup(texte: str) -> bool:
    """Dit si un texte porte encore du balisage, visible ou échappé."""
    return bool(HTML_TAG.search(texte)) or "&lt;" in texte or "&amp;" in texte


def strip_markup(value: str) -> str:
    """Retire le balisage, y compris lorsqu'il a été échappé deux fois.

    Certains flux publient un résumé doublement échappé : `&amp;lt;p&amp;gt;`.
    Le premier passage rend `&lt;p&gt;`, que la lecture des entités transforme
    en `<p>` visible à l'écran. Il faut donc recommencer tant que du balisage
    réapparaît, visible ou encore échappé, mais seulement dans ce cas : un
    « < » isolé n'est pas du balisage et doit être laissé tel quel.
    """
    if "<" not in value and "&" not in value:
        return value.strip()
    for _ in range(MAX_UNESCAPE_PASSES):
        nettoye = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
        if nettoye == value or not has_hidden_markup(nettoye):
            return nettoye
        value = nettoye
    return value


def clean_text(value: Any, limit: int = 1800) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = strip_markup(value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def clean_summary(value: Any, limit: int = 1800) -> str:
    """Nettoie un résumé et le débarrasse de la mention ajoutée par WordPress.

    Rend une chaîne vide si le résumé ne contenait que cette mention : mieux
    vaut pas de résumé qu'une phrase qui ne dit rien de l'article.
    """
    texte = clean_text(value, limit)
    if not texte:
        return ""
    return re.sub(r"\s+", " ", BOILERPLATE.sub(" ", texte)).strip()
