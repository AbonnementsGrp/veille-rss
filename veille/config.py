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


def load_config(path: Path | None = None) -> dict[str, Any]:
    with (path or CONFIG_PATH).open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    if not isinstance(cfg.get("sites"), list):
        raise ValueError("La section 'sites' de config/sites.yml est absente ou invalide.")
    return cfg
