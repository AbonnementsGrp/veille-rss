"""Session HTTP partagée et reconnaissance d'un contenu de type flux."""

from __future__ import annotations

from typing import Any

import requests


def request_session(settings: dict[str, Any]) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": settings.get("user_agent", "VeilleRSS/1.0"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
        "Cache-Control": "no-cache",
    })
    return session


def is_feed_content(response: requests.Response) -> bool:
    """Détecte un flux RSS/Atom, y compris servi avec un content-type erroné."""
    content_type = response.headers.get("content-type", "").lower()
    head = response.text[:1000].lower()
    return any(x in content_type for x in ("rss", "atom", "xml")) or "<rss" in head or "<feed" in head
