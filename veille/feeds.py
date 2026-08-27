"""Lecture d'un flux RSS/Atom et découverte automatique du flux d'un site."""

from __future__ import annotations

import feedparser
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from veille.dates import normalize_date
from veille.fetch import is_feed_content
from veille.models import Item, dedupe
from veille.text import clean_text

# Emplacements conventionnels testés quand le site ne déclare pas son flux.
FEED_PATH_CANDIDATES = ("/feed/", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml")


def parse_feed_bytes(content: bytes, source: str, max_items: int) -> list[Item]:
    parsed = feedparser.parse(content)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        raise RuntimeError(f"Flux RSS invalide : {getattr(parsed, 'bozo_exception', 'erreur inconnue')}")
    items: list[Item] = []
    for entry in parsed.entries[:max_items]:
        title = clean_text(entry.get("title"))
        link = str(entry.get("link") or "").strip()
        if not title or not link:
            continue
        published = normalize_date(
            entry.get("published") or entry.get("updated") or entry.get("created")
            or entry.get("published_parsed") or entry.get("updated_parsed")
        )
        items.append(Item(
            source=source,
            title=title,
            link=link,
            description=clean_text(entry.get("summary") or entry.get("description") or entry.get("content")),
            published=published,
        ))
    return dedupe(items)


def try_feed(session: requests.Session, url: str, timeout: int) -> str | None:
    """Rend l'URL finale si elle sert un flux exploitable, sinon None."""
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        if response.ok and is_feed_content(response) and parse_feed_bytes(response.content, "test", 1):
            return response.url
    except Exception:
        return None
    return None


def declared_feeds(soup: BeautifulSoup, base_url: str) -> list[str]:
    """URL des flux que la page déclare elle-même via <link rel="alternate">."""
    trouves = []
    for link in soup.select('link[rel~="alternate"][href]'):
        typ = (link.get("type") or "").lower()
        titre = (link.get("title") or "").lower()
        if any(terme in typ + " " + titre for terme in ("rss", "atom", "feed", "xml")):
            trouves.append(urljoin(base_url, link["href"]))
    return trouves


def discover_feed(session: requests.Session, page_url: str, timeout: int) -> str | None:
    """Cherche le flux natif le plus pertinent pour une page d'actualités.

    L'ordre compte. Le flux propre à la rubrique passe avant celui que la page
    déclare : WordPress annonce le flux global du site dans son <link
    rel="alternate">, or le flux d'une section est thématiquement plus juste.
    ADN Tourisme en est l'exemple : son flux racine mêle actualités et offres
    d'emploi, quand /publications/actus/feed/ ne sert que les actualités.
    """
    try:
        response = session.get(page_url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except Exception:
        return None
    if is_feed_content(response):
        try:
            if feedparser.parse(response.content).entries:
                return response.url
        except Exception:
            pass
    soup = BeautifulSoup(response.text, "html.parser")
    parsed = urlparse(response.url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")

    propres = [f"{base}{path}/feed/", f"{base}{path}/feed"] if path else []
    racine = [f"{base}{suffixe}" for suffixe in FEED_PATH_CANDIDATES]
    deja: set[str] = set()
    for candidate in propres + declared_feeds(soup, response.url) + racine:
        if candidate in deja:
            continue
        deja.add(candidate)
        trouve = try_feed(session, candidate, timeout)
        if trouve:
            return trouve
    return None
