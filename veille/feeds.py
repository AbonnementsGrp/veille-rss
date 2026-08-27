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


def discover_feed(session: requests.Session, page_url: str, timeout: int) -> str | None:
    """Cherche un flux natif : la page elle-même, sa balise <link>, puis les
    emplacements conventionnels. Rend None si aucun flux exploitable."""
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
    for link in soup.select('link[rel~="alternate"][href]'):
        typ = (link.get("type") or "").lower()
        title = (link.get("title") or "").lower()
        if any(term in typ + " " + title for term in ("rss", "atom", "feed", "xml")):
            candidate = urljoin(response.url, link["href"])
            try:
                rr = session.get(candidate, timeout=timeout)
                if rr.ok and parse_feed_bytes(rr.content, "test", 1):
                    return candidate
            except Exception:
                continue
    parsed = urlparse(response.url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    candidates = [f"{base}{path}/feed/", f"{base}{path}/feed"]
    candidates += [f"{base}{suffix}" for suffix in FEED_PATH_CANDIDATES]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            rr = session.get(candidate, timeout=timeout, allow_redirects=True)
            if rr.ok and is_feed_content(rr) and parse_feed_bytes(rr.content, "test", 1):
                return rr.url
        except Exception:
            continue
    return None
