"""Chemins du projet et lecture de la configuration des sources."""

from __future__ import annotations

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


def ordered_sites(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Rend les sources dans l'ordre d'affichage.

    Trois critères : le domaine, selon la liste `settings.themes` ; puis la clé
    `order` de la source ; puis sa position dans le fichier. Un domaine absent
    de la liste passe en dernier, sous « Autres ».
    """
    themes = [str(t) for t in ((cfg.get("settings") or {}).get("themes") or [])]
    rang = {theme: n for n, theme in enumerate(themes)}
    apres = len(rang)

    def cle(paire: tuple[int, dict[str, Any]]) -> tuple[int, float, int]:
        index, site = paire
        return (rang.get(theme_of(site), apres), float(site.get("order", index)), index)

    return [site for _, site in sorted(enumerate(cfg["sites"]), key=cle)]


def load_config(path: Path | None = None) -> dict[str, Any]:
    with (path or CONFIG_PATH).open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    if not isinstance(cfg.get("sites"), list):
        raise ValueError("La section 'sites' de config/sites.yml est absente ou invalide.")
    return cfg
