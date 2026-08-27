"""Représentation d'un article et déduplication."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class Item:
    source: str
    title: str
    link: str
    description: str = ""
    published: str = ""
    first_seen: str = ""

    @property
    def uid(self) -> str:
        raw = f"{self.source}|{self.link.rstrip('/')}|{self.title}".encode("utf-8", errors="ignore")
        return hashlib.sha256(raw).hexdigest()


def dedupe(items: list[Item]) -> list[Item]:
    """Conserve la première occurrence de chaque lien, dans l'ordre reçu."""
    seen: set[str] = set()
    result: list[Item] = []
    for item in items:
        key = item.link.rstrip("/").lower() or item.uid
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
