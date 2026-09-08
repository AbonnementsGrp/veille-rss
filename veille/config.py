"""Chemins du projet et lecture de la configuration des sources."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "sites.yml"
PUBLIC_DIR = ROOT / "public"
DATA_DIR = ROOT / "data"
HISTORY_PATH = DATA_DIR / "history.json"
STATUS_PATH = PUBLIC_DIR / "status.json"

BASE_URL = "https://abonnementsgrp.github.io/veille-rss/"


AUTRES = "Autres"


def theme_of(site: dict[str, Any]) -> str:
    return str(site.get("theme") or AUTRES).strip() or AUTRES


def sort_key(texte: str) -> str:
    """Clé de tri alphabétique insensible à la casse et aux accents.

    « Éducation » se range à E, « école » à e : les accents sont décomposés
    puis écartés, et la casse est neutralisée. Indépendant du réglage de langue
    du système, donc identique sur un poste Windows et sur la CI Linux.
    """
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c)).casefold()


def display_name(site: dict[str, Any]) -> str:
    return str(site.get("short_name") or site["name"])


def ordered_sites(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Rend les sources dans l'ordre d'affichage.

    Domaines par ordre alphabétique, « Autres » en dernier ; dans chaque
    domaine, sources par ordre alphabétique de leur nom affiché. Le tri étant
    stable, deux sources de même nom gardent l'ordre du fichier.
    """
    def cle(site: dict[str, Any]) -> tuple[bool, str, str]:
        theme = theme_of(site)
        return (theme == AUTRES, sort_key(theme), sort_key(display_name(site)))

    return sorted(cfg["sites"], key=cle)


def load_config(path: Path | None = None) -> dict[str, Any]:
    with (path or CONFIG_PATH).open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    if not isinstance(cfg.get("sites"), list):
        raise ValueError("La section 'sites' de config/sites.yml est absente ou invalide.")
    return cfg
