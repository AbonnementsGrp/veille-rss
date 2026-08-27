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
from veille.text import clean_summary

log = logging.getLogger(__name__)

DATE_FIELDS = ("published", "first_seen")


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Remet un enregistrement d'historique aux normes courantes.

    Les dates d'abord : des versions antérieures ont enregistré `published` au
    format RFC-822 ("Wed, 03 Jun 2026 19:04:18 +0000"), ce qui faussait tout
    tri effectué sur la chaîne brute.

    Le résumé ensuite : les mentions ajoutées par WordPress et le balisage
    doublement échappé y ont aussi été enregistrés, et l'historique complétant
    chaque flux, ils continueraient d'être publiés.
    """
    for field in DATE_FIELDS:
        value = record.get(field)
        if value:
            record[field] = normalize_date(value)
    if record.get("description"):
        record["description"] = clean_summary(record["description"])
    return record


# Ancien nom, conservé pour ne pas casser un appel existant.
normalize_record_dates = normalize_record


def load_history(path: Path | None = None) -> dict[str, dict[str, Any]]:
    path = path or HISTORY_PATH
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {uid: normalize_record(record) for uid, record in raw.items() if isinstance(record, dict)}
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


def remove_source(history: dict[str, dict[str, Any]], source: str) -> int:
    """Retire de l'historique toutes les entrées d'une source, et les compte.

    À utiliser quand la méthode d'extraction d'une source change : les
    articles récoltés par l'ancienne, devenus non représentatifs, continuent
    sinon d'être republiés puisque l'historique complète chaque flux.
    """
    vises = [uid for uid, record in history.items() if record.get("source") == source]
    for uid in vises:
        del history[uid]
    return len(vises)


__all__ = [
    "history_items_for_source",
    "normalize_record",
    "remove_source",
    "load_history",
    "normalize_record_dates",
    "save_history",
]
