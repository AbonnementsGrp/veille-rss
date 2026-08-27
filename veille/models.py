"""Représentation d'un article et déduplication."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from veille.urls import clean_link


@dataclass
class Item:
    source: str
    title: str
    link: str
    description: str = ""
    published: str = ""
    first_seen: str = ""

    def __post_init__(self) -> None:
        # Normalisé ici, donc pour toutes les sources : le lien porte l'identité
        # de l'article, il ne doit pas dépendre des paramètres de campagne.
        self.link = clean_link(self.link)

    @property
    def uid(self) -> str:
        raw = f"{self.source}|{self.link.rstrip('/')}|{self.title}".encode("utf-8", errors="ignore")
        return hashlib.sha256(raw).hexdigest()


def dedupe(items: list[Item]) -> list[Item]:
    """Conserve la première occurrence de chaque article, dans l'ordre reçu.

    Deux clés, car un même article peut se présenter sous deux formes. Le lien,
    d'abord. Puis le titre au sein d'une source : Drupal publie un rapport à la
    fois comme actualité et comme page de rapport, sous deux URL distinctes.
    Le titre est associé à la source, pour que deux sources qui couvrent le même
    sujet restent toutes deux visibles dans le flux consolidé.
    """
    liens: set[str] = set()
    titres: set[tuple[str, str]] = set()
    result: list[Item] = []
    for item in items:
        lien = item.link.rstrip("/").lower() or item.uid
        titre = (item.source, " ".join(item.title.lower().split()))
        if lien in liens or (titre[1] and titre in titres):
            continue
        liens.add(lien)
        titres.add(titre)
        result.append(item)
    return result
