"""Historique des articles vus, conservé entre deux exécutions.

L'historique sert à deux choses : compter les nouveautés d'une exécution et
republier les articles d'une source momentanément indisponible.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from veille.config import HISTORY_PATH
from veille.dates import EPOCH, normalize_date, parse_date_for_feed
from veille.models import Item

log = logging.getLogger(__name__)

DATE_FIELDS = ("published", "first_seen")


def normalize_record_dates(record: dict[str, Any]) -> dict[str, Any]:
    """Aligne les dates d'un enregistrement sur l'ISO 8601 UTC.

    Les versions antérieures du script ont enregistré `published` au format
    RFC-822 ("Wed, 03 Jun 2026 19:04:18 +0000"), ce qui faussait tout tri
    effectué sur la chaîne brute.
    """
    for field in DATE_FIELDS:
        value = record.get(field)
        if value:
            record[field] = normalize_date(value)
    return record


def load_history(path: Path | None = None) -> dict[str, dict[str, Any]]:
    path = path or HISTORY_PATH
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {uid: normalize_record_dates(record) for uid, record in raw.items() if isinstance(record, dict)}
    except Exception as exc:
        log.warning("Historique illisible (%s). Un historique vide sera utilisé.", exc)
        return {}


def save_history(history: dict[str, dict[str, Any]], limit: int, path: Path | None = None) -> None:
    path = path or HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(history.values(), key=lambda r: r.get("first_seen", ""), reverse=True)[:limit]
    path.write_text(
        json.dumps({r["uid"]: r for r in records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def history_items_for_source(history: dict[str, dict[str, Any]], source: str, limit: int) -> list[Item]:
    """Rend les articles connus d'une source, du plus récent au plus ancien."""
    records = [r for r in history.values() if r.get("source") == source]
    records.sort(key=lambda r: parse_date_for_feed(r.get("published") or r.get("first_seen") or "") or EPOCH, reverse=True)
    return [Item(
        source=r.get("source", source), title=r.get("title", ""), link=r.get("link", ""),
        description=r.get("description", ""), published=r.get("published", ""), first_seen=r.get("first_seen", "")
    ) for r in records[:limit] if r.get("title") and r.get("link")]


__all__ = [
    "history_items_for_source",
    "load_history",
    "normalize_record_dates",
    "save_history",
]
