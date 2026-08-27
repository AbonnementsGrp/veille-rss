"""Orchestration d'une exécution complète de la veille.

Pour chaque source : flux officiel s'il est configuré, sinon flux natif
découvert, sinon extraction HTML. Une source en échec n'interrompt jamais le
traitement des autres — elle republie son historique si elle en a un.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from typing import Any
from urllib.parse import urljoin

from veille.config import BASE_URL, PUBLIC_DIR, STATUS_PATH, load_config
from veille.dates import item_sort_key, utc_now
from veille.extract import scrape_page
from veille.feeds import discover_feed, parse_feed_bytes
from veille.fetch import request_session
from veille.history import history_items_for_source, load_history, save_history
from veille.models import Item, dedupe
from veille.output import write_dashboard, write_feed, write_opml

log = logging.getLogger(__name__)


def output_name_for(site: dict[str, Any]) -> str:
    """Nom de fichier du flux d'une source, déduit du nom si non configuré."""
    configured = site.get("output")
    if configured:
        return str(configured)
    return re.sub(r"[^a-z0-9]+", "-", site["name"].lower()).strip("-") + ".xml"


def resolve_feed_url(session: Any, site: dict[str, Any], timeout: int) -> str:
    """Rend l'URL du flux à utiliser : celle configurée, sinon celle découverte.

    Résolue avant toute lecture, afin que `status.json` conserve l'URL testée
    même quand la lecture échoue ensuite.
    """
    return site.get("official_feed") or discover_feed(session, site["url"], timeout) or ""


def fetch_items(session: Any, site: dict[str, Any], feed_url: str, timeout: int, max_items: int) -> tuple[list[Item], str]:
    """Lit les articles d'une source et rend (articles, méthode employée)."""
    if feed_url:
        response = session.get(feed_url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        items = parse_feed_bytes(response.content, site["name"], max_items)
        method = "flux officiel" if site.get("official_feed") else "flux détecté"
    else:
        items, method = scrape_page(session, site, timeout, max_items)
    if not items:
        raise RuntimeError("Aucun article détecté sur la page")
    return items, method


def record_in_history(items: list[Item], history: dict[str, dict[str, Any]]) -> int:
    """Enregistre les articles et rend le nombre de nouveautés."""
    seen_at = utc_now().isoformat()
    new_count = 0
    for item in items:
        if not item.first_seen:
            item.first_seen = seen_at
        if item.uid not in history:
            new_count += 1
            history[item.uid] = {**asdict(item), "uid": item.uid, "first_seen": seen_at}
        else:
            item.first_seen = history[item.uid].get("first_seen", seen_at)
            history[item.uid].update({**asdict(item), "uid": item.uid})
    return new_count


def run() -> int:
    cfg = load_config()
    settings = cfg.get("settings") or {}
    sites = cfg["sites"]
    timeout = int(settings.get("request_timeout", 30))
    max_items = int(settings.get("max_items_per_feed", 60))
    history_limit = int(settings.get("max_history_items", 1000))
    keep_previous = bool(settings.get("keep_previous_on_error", True))
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    history = load_history()
    session = request_session(settings)
    statuses: list[dict[str, Any]] = []
    all_items: list[Item] = []
    new_count = 0

    for site in sites:
        source = site["name"]
        output_name = output_name_for(site)
        feed_url = ""
        try:
            feed_url = resolve_feed_url(session, site, timeout)
            items, method = fetch_items(session, site, feed_url, timeout, max_items)
            new_count += record_in_history(items, history)
            source_items = dedupe(items + history_items_for_source(history, source, max_items))[:max_items]
            write_feed(source_items, source, f"Actualités de {source}", PUBLIC_DIR / output_name, site["url"], urljoin(BASE_URL, output_name))
            all_items.extend(source_items)
            statuses.append({"site": source, "url": site["url"], "status": "ok", "method": method, "items": len(source_items), "feed": output_name, "source_feed": feed_url})
            log.info("%s : %d article(s) via %s", source, len(source_items), method)
        except Exception as exc:
            previous = history_items_for_source(history, source, max_items) if keep_previous else []
            if previous:
                write_feed(previous, source, f"Actualités de {source}", PUBLIC_DIR / output_name, site["url"], urljoin(BASE_URL, output_name))
                all_items.extend(previous)
            statuses.append({"site": source, "url": site["url"], "status": "error", "method": "historique conservé" if previous else "échec", "items": len(previous), "feed": output_name, "error": str(exc), "source_feed": feed_url})
            log.error("%s : %s", source, exc)

    merged = dedupe(all_items)
    merged.sort(key=item_sort_key, reverse=True)
    merged = merged[:history_limit]
    merged_output = settings.get("merged_output", "veille.xml")
    write_feed(
        merged,
        settings.get("merged_feed_name", "Veille RSS globale"),
        settings.get("merged_feed_description", "Flux consolidé des sources de veille"),
        PUBLIC_DIR / merged_output,
        BASE_URL,
        urljoin(BASE_URL, merged_output),
    )
    save_history(history, history_limit)
    payload = {
        "generated_at": utc_now().isoformat(),
        "sites_total": len(sites),
        "sites_ok": sum(s["status"] == "ok" for s in statuses),
        "sites_error": sum(s["status"] == "error" for s in statuses),
        "new_items": new_count,
        "merged_items": len(merged),
        "sites": statuses,
    }
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_opml(statuses, BASE_URL)
    write_dashboard(payload, settings.get("site_title", "Tableau de bord de la veille RSS"))
    log.info("Bilan : %d source(s), %d OK, %d erreur(s), %d article(s)", payload["sites_total"], payload["sites_ok"], payload["sites_error"], payload["merged_items"])
    return 0
