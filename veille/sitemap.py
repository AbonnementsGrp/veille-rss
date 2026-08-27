"""Extraction depuis un plan de site (sitemap.xml).

Dernier recours pour un site entièrement rendu en JavaScript : ses pages ne
livrent aucun titre à un simple client HTTP, mais son plan de site publie les
URL et leur date de dernière modification. C'est le cas de l'ANAP, dont le
robots.txt déclare lui-même ses plans de site.

Le titre est alors déduit du dernier segment de l'URL, seule information
lisible disponible. Le résultat est imparfait — accents et majuscules d'origine
sont perdus — mais reste préférable à une source absente du flux.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import unquote, urlsplit

from veille.dates import item_sort_key, normalize_date
from veille.models import Item, dedupe

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
# Identifiant technique que Salesforce accole au slug.
ID_SUFFIX = re.compile(r"-[A-Z0-9]{15,}$")
MIN_TITLE_LENGTH = 5


def title_from_slug(url: str) -> str:
    """Reconstitue un titre lisible depuis le dernier segment d'une URL."""
    segment = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    segment = ID_SUFFIX.sub("", unquote(segment))
    mots = segment.replace("_", " ").replace("-", " ").split()
    if not mots:
        return ""
    texte = " ".join(mots)
    return texte[0].upper() + texte[1:]


def parse_sitemap(content: bytes, source: str, max_items: int) -> list[Item]:
    """Lit un plan de site et rend ses URL, de la plus récente à la plus ancienne."""
    root = ET.fromstring(content)
    if root.tag.endswith("sitemapindex"):
        raise RuntimeError(
            "ce plan de site est un index : indiquer l'un des plans qu'il référence"
        )
    entrees: list[Item] = []
    for url in root.findall("sm:url", SITEMAP_NS):
        lien = (url.findtext("sm:loc", "", SITEMAP_NS) or "").strip()
        if not lien:
            continue
        titre = title_from_slug(lien)
        if len(titre) < MIN_TITLE_LENGTH:
            continue
        entrees.append(Item(
            source=source,
            title=titre,
            link=lien,
            published=normalize_date(url.findtext("sm:lastmod", "", SITEMAP_NS)),
        ))
    entrees.sort(key=item_sort_key, reverse=True)
    return dedupe(entrees)[:max_items]


def items_from_sitemap(session: Any, url: str, source: str, timeout: int, max_items: int) -> list[Item]:
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    items = parse_sitemap(response.content, source, max_items)
    if not items:
        raise RuntimeError(f"{url} ne contient aucune URL exploitable")
    return items
