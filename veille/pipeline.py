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
from veille.enrich import describe_article
from veille.extract import scrape_page
from veille.feeds import discover_feed, parse_feed_bytes
from veille.fetch import is_feed_content, request_session
from veille.history import history_items_for_source, load_history, save_history
from veille.models import Item, dedupe
from veille.sitemap import items_from_sitemap
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

    `mode: page` désactive la découverte : certains sites servent un flux
    racine qui n'a rien à voir avec la rubrique suivie, la page est alors la
    seule source fiable.
    """
    if site.get("official_feed"):
        return str(site["official_feed"])
    if str(site.get("mode", "")).lower() in ("page", "sitemap"):
        return ""
    return discover_feed(session, site["url"], timeout) or ""


def read_feed(session: Any, url: str, source: str, timeout: int, max_items: int) -> list[Item]:
    """Lit un flux à une URL donnée, en refusant ce qui n'en est pas un.

    Un `/feed/` WordPress désactivé renvoie la page HTML de la rubrique avec un
    code 200 : sans ce contrôle, l'erreur remontée parle de XML mal formé au
    lieu de dire que l'URL ne sert pas un flux.
    """
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    if not is_feed_content(response):
        type_recu = response.headers.get("content-type", "inconnu").split(";")[0]
        raise RuntimeError(f"{url} ne sert pas un flux (contenu {type_recu})")
    return parse_feed_bytes(response.content, source, max_items)


def fetch_items(session: Any, site: dict[str, Any], feed_url: str, timeout: int, max_items: int) -> tuple[list[Item], str]:
    """Lit les articles d'une source et rend (articles, méthode employée).

    Un flux configuré qui s'avère inexploitable ne condamne pas la source : le
    traitement se replie sur l'extraction de la page d'actualités, qui reste
    thématiquement juste là où un flux découvert au hasard du site ne l'est pas.

    `mode: sitemap` court-circuite tout cela : c'est le seul recours pour un
    site dont les pages sont rendues en JavaScript.
    """
    if str(site.get("mode", "")).lower() == "sitemap":
        plan = site.get("sitemap") or ""
        if not plan:
            raise RuntimeError("mode sitemap sans clé 'sitemap' dans la configuration")
        return items_from_sitemap(session, str(plan), site["name"], timeout, max_items), "plan de site"

    echec_flux = ""
    if feed_url:
        try:
            items = read_feed(session, feed_url, site["name"], timeout, max_items)
            if items:
                return items, "flux officiel" if site.get("official_feed") else "flux détecté"
            echec_flux = "flux sans article exploitable"
        except Exception as exc:
            echec_flux = str(exc)
        log.warning("%s : %s. Repli sur la page d'actualités.", site["name"], echec_flux)

    items, method = scrape_page(session, site, timeout, max_items)
    if not items:
        detail = f"{echec_flux} ; aucun article détecté sur la page" if echec_flux else "Aucun article détecté sur la page"
        raise RuntimeError(detail)
    return items, f"repli : {method}" if echec_flux else method


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
            connu = history[item.uid]
            item.first_seen = connu.get("first_seen", seen_at)
            fiche = {**asdict(item), "uid": item.uid}
            # Un résumé déjà obtenu ne doit pas être effacé par un flux qui n'en
            # fournit pas : il a pu être lu sur la page de l'article.
            if not fiche["description"] and connu.get("description"):
                fiche["description"] = connu["description"]
            connu.update(fiche)
    return new_count


def reuse_known_descriptions(items: list[Item], history: dict[str, dict[str, Any]]) -> None:
    """Reprend le résumé déjà connu d'un article dont le flux n'en donne pas.

    Ne coûte rien, donc jamais soumis au budget réseau de l'enrichissement.
    """
    for item in items:
        if item.description:
            continue
        connu = (history.get(item.uid) or {}).get("description")
        if connu:
            item.description = connu


def enrich_descriptions(session: Any, items: list[Item], history: dict[str, dict[str, Any]],
                        budget: int, timeout: int) -> int:
    """Complète les résumés encore manquants en lisant la page des articles.

    Rend le nombre de pages visitées. Chaque article n'est tenté qu'une fois :
    l'historique retient la tentative, pour ne pas redemander indéfiniment une
    page qui n'a rien à offrir. Le budget étant global et consommé dans l'ordre
    des sources, les dernières sources sont servies aux exécutions suivantes.

    Les sources en `mode: sitemap` sont exclues par l'appelant : leurs pages
    sont rendues en JavaScript, elles ne livreraient aucun résumé.
    """
    visitees = 0
    for item in items:
        if visitees >= budget:
            break
        if item.description:
            continue
        fiche = history.get(item.uid)
        if fiche is None or fiche.get("description_checked"):
            continue
        visitees += 1
        fiche["description_checked"] = True
        try:
            resume = describe_article(session, item.link, timeout)
        except Exception as exc:
            log.debug("Résumé indisponible pour %s (%s)", item.link, exc)
            continue
        if resume:
            item.description = resume
            fiche["description"] = resume
    return visitees


def run() -> int:
    cfg = load_config()
    settings = cfg.get("settings") or {}
    sites = cfg["sites"]
    timeout = int(settings.get("request_timeout", 30))
    max_items = int(settings.get("max_items_per_feed", 60))
    history_limit = int(settings.get("max_history_items", 1000))
    keep_previous = bool(settings.get("keep_previous_on_error", True))
    enrich_budget = int(settings.get("max_enrichments_per_run", 25)) if settings.get("enrich_descriptions", True) else 0
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
            # Sur le flux publié, et non sur les seuls articles du jour : les
            # articles venus de l'historique méritent aussi un résumé.
            reuse_known_descriptions(source_items, history)
            if enrich_budget > 0 and str(site.get("mode", "")).lower() != "sitemap":
                enrich_budget -= enrich_descriptions(session, source_items, history, enrich_budget, timeout)
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
