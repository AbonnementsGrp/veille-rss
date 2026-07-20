from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "sites.yml"
PUBLIC_DIR = ROOT / "public"
DATA_DIR = ROOT / "data"
HISTORY_PATH = DATA_DIR / "history.json"
STATUS_PATH = PUBLIC_DIR / "status.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("veille-rss")

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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(value: Any, limit: int = 1800) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def normalize_date(value: Any) -> str:
    if not value:
        return ""
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (tuple, list)) and len(value) >= 6:
            dt = datetime(*value[:6], tzinfo=timezone.utc)
        else:
            dt = date_parser.parse(str(value), dayfirst=True, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def parse_date_for_feed(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    if not isinstance(cfg.get("sites"), list):
        raise ValueError("La section 'sites' de config/sites.yml est absente ou invalide.")
    return cfg


def load_history() -> dict[str, dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return {}
    try:
        raw = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:
        log.warning("Historique illisible (%s). Un historique vide sera utilisé.", exc)
        return {}


def save_history(history: dict[str, dict[str, Any]], limit: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = sorted(history.values(), key=lambda r: r.get("first_seen", ""), reverse=True)[:limit]
    HISTORY_PATH.write_text(
        json.dumps({r["uid"]: r for r in records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    content_type = response.headers.get("content-type", "").lower()
    head = response.text[:1000].lower()
    return any(x in content_type for x in ("rss", "atom", "xml")) or "<rss" in head or "<feed" in head


def parse_feed_bytes(content: bytes, source: str, max_items: int) -> list[Item]:
    parsed = feedparser.parse(content)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        raise RuntimeError(f"Flux RSS invalide : {getattr(parsed, 'bozo_exception', 'erreur inconnue')}")
    items: list[Item] = []
    for entry in parsed.entries[:max_items]:
        title = clean_text(entry.get("title"))
        link = str(entry.get("link") or "").strip()
        if not title or not link:
            continue
        published = normalize_date(
            entry.get("published") or entry.get("updated") or entry.get("created")
            or entry.get("published_parsed") or entry.get("updated_parsed")
        )
        items.append(Item(
            source=source,
            title=title,
            link=link,
            description=clean_text(entry.get("summary") or entry.get("description") or entry.get("content")),
            published=published,
        ))
    return dedupe(items)


def discover_feed(session: requests.Session, page_url: str, timeout: int) -> str | None:
    try:
        response = session.get(page_url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except Exception:
        return None
    if is_feed_content(response):
        try:
            if feedparser.parse(response.content).entries:
                return response.url
        except Exception:
            pass
    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.select('link[rel~="alternate"][href]'):
        typ = (link.get("type") or "").lower()
        title = (link.get("title") or "").lower()
        if any(term in typ + " " + title for term in ("rss", "atom", "feed", "xml")):
            candidate = urljoin(response.url, link["href"])
            try:
                rr = session.get(candidate, timeout=timeout)
                if rr.ok and parse_feed_bytes(rr.content, "test", 1):
                    return candidate
            except Exception:
                continue
    parsed = urlparse(response.url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    candidates = [
        f"{base}{path}/feed/", f"{base}{path}/feed", f"{base}/feed/", f"{base}/rss.xml",
        f"{base}/feed.xml", f"{base}/atom.xml", f"{base}/index.xml",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            rr = session.get(candidate, timeout=timeout, allow_redirects=True)
            if rr.ok and is_feed_content(rr) and parse_feed_bytes(rr.content, "test", 1):
                return rr.url
        except Exception:
            continue
    return None


def first_match(node: Any, selectors: Iterable[str]) -> Any | None:
    for selector in selectors:
        try:
            result = node.select_one(selector)
            if result:
                return result
        except Exception:
            continue
    return None


def parse_json_ld(soup: BeautifulSoup, source: str, base_url: str, max_items: int) -> list[Item]:
    found: list[Item] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        stack: list[Any] = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, list):
                stack.extend(obj)
                continue
            if not isinstance(obj, dict):
                continue
            for key in ("@graph", "itemListElement"):
                if key in obj:
                    stack.append(obj[key])
            if "item" in obj and isinstance(obj["item"], dict):
                stack.append(obj["item"])
            typ = obj.get("@type", "")
            types = " ".join(typ) if isinstance(typ, list) else str(typ)
            if any(term in types.lower() for term in ("article", "newsarticle", "blogposting")):
                title = clean_text(obj.get("headline") or obj.get("name"))
                link: Any = obj.get("url") or obj.get("mainEntityOfPage")
                if isinstance(link, dict):
                    link = link.get("@id") or link.get("url")
                if title and link:
                    found.append(Item(
                        source=source,
                        title=title,
                        link=urljoin(base_url, str(link)),
                        description=clean_text(obj.get("description")),
                        published=normalize_date(obj.get("datePublished") or obj.get("dateModified")),
                    ))
            if len(found) >= max_items:
                return dedupe(found)
    return dedupe(found)


def extract_with_selectors(soup: BeautifulSoup, site: dict[str, Any], max_items: int) -> list[Item]:
    selectors = site.get("selectors") or {}
    item_selectors = selectors.get("item") or ["article", ".views-row", ".news-item", ".post", ".card", ".item"]
    title_selectors = selectors.get("title") or ["h1 a", "h2 a", "h3 a", ".title a", ".entry-title a"]
    desc_selectors = selectors.get("description") or [".excerpt", ".summary", ".entry-summary", ".description", "p"]
    date_selectors = selectors.get("date") or ["time", ".date", ".published", "[datetime]"]
    nodes: list[Any] = []
    for selector in item_selectors:
        try:
            candidates = soup.select(selector)
        except Exception:
            continue
        if len(candidates) >= 2:
            nodes = candidates
            break
    items: list[Item] = []
    for node in nodes:
        title_node = first_match(node, title_selectors)
        if not title_node:
            continue
        anchor = title_node if title_node.name == "a" else title_node.find("a", href=True)
        if not anchor or not anchor.get("href"):
            continue
        title = clean_text(title_node.get_text(" ", strip=True))
        if len(title) < 5:
            continue
        desc_node = first_match(node, desc_selectors)
        date_node = first_match(node, date_selectors)
        raw_date = ""
        if date_node:
            raw_date = date_node.get("datetime") or date_node.get("content") or date_node.get_text(" ", strip=True)
        items.append(Item(
            source=site["name"],
            title=title,
            link=urljoin(site["url"], anchor["href"]),
            description=clean_text(desc_node.get_text(" ", strip=True) if desc_node else ""),
            published=normalize_date(raw_date),
        ))
        if len(items) >= max_items:
            break
    return dedupe(items)


def generic_link_score(anchor: Any, base_host: str, patterns: list[str]) -> int:
    href = anchor.get("href") or ""
    text = clean_text(anchor.get_text(" ", strip=True), 300)
    absolute = urljoin(f"https://{base_host}/", href)
    parsed = urlparse(absolute)
    if parsed.netloc and parsed.netloc != base_host:
        return -100
    if not text or len(text) < 12 or len(text) > 240:
        return -100
    low = (href + " " + text).lower()
    if href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return -100
    if any(x in low for x in ("connexion", "contact", "mentions-legales", "politique-de-confidentialite", "cookie", "facebook", "linkedin", "instagram", "twitter")):
        return -100
    score = 0
    if anchor.find_parent(["article", "main"]): score += 4
    if anchor.find_parent(["h1", "h2", "h3", "h4"]): score += 5
    if any(p.lower() in href.lower() for p in patterns): score += 8
    if any(x in href.lower() for x in ("actualit", "news", "article", "publication", "communique", "blog")): score += 5
    if re.search(r"/20\d{2}/|\d{4}-\d{2}-\d{2}", href): score += 3
    if len(text) >= 25: score += 2
    return score


def extract_generic_links(soup: BeautifulSoup, site: dict[str, Any], max_items: int) -> list[Item]:
    base = urlparse(site["url"])
    patterns = site.get("link_patterns") or []
    ranked: list[tuple[int, Item]] = []
    for anchor in soup.select("a[href]"):
        score = generic_link_score(anchor, base.netloc, patterns)
        if score < 5:
            continue
        href = urljoin(site["url"], anchor.get("href"))
        title = clean_text(anchor.get_text(" ", strip=True), 300)
        container = anchor.find_parent(["article", "li", "div", "section"])
        description = ""
        published = ""
        if container:
            p = container.find("p")
            if p:
                description = clean_text(p.get_text(" ", strip=True))
            time_node = container.find("time") or container.select_one(".date, .published, [datetime]")
            if time_node:
                published = normalize_date(time_node.get("datetime") or time_node.get("content") or time_node.get_text(" ", strip=True))
        ranked.append((score, Item(site["name"], title, href, description, published)))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return dedupe([item for _, item in ranked])[:max_items]


def scrape_page(session: requests.Session, site: dict[str, Any], timeout: int, max_items: int) -> tuple[list[Item], str]:
    response = session.get(site["url"], timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for selector in ("script", "style", "noscript", "svg"):
        for node in soup.select(selector):
            node.decompose()
    json_items = parse_json_ld(soup, site["name"], response.url, max_items)
    selector_items = extract_with_selectors(soup, {**site, "url": response.url}, max_items)
    generic_items = extract_generic_links(soup, {**site, "url": response.url}, max_items)
    combined = dedupe(json_items + selector_items + generic_items)[:max_items]
    if json_items:
        method = "json_ld+html"
    elif selector_items:
        method = "html_selectors"
    else:
        method = "generic_links"
    return combined, method


def dedupe(items: list[Item]) -> list[Item]:
    seen: set[str] = set()
    result: list[Item] = []
    for item in items:
        key = item.link.rstrip("/").lower() or item.uid
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def history_items_for_source(history: dict[str, dict[str, Any]], source: str, limit: int) -> list[Item]:
    records = [r for r in history.values() if r.get("source") == source]
    records.sort(key=lambda r: r.get("published") or r.get("first_seen") or "", reverse=True)
    return [Item(
        source=r.get("source", source), title=r.get("title", ""), link=r.get("link", ""),
        description=r.get("description", ""), published=r.get("published", ""), first_seen=r.get("first_seen", "")
    ) for r in records[:limit] if r.get("title") and r.get("link")]


def item_sort_key(item: Item) -> str:
    return item.published or item.first_seen or ""


def write_feed(items: list[Item], title: str, description: str, output: Path, home_url: str, self_url: str = "") -> None:
    fg = FeedGenerator()
    fg.id(home_url)
    fg.title(title)
    fg.description(description)
    fg.language("fr")
    fg.link(href=home_url, rel="alternate")
    if self_url:
        fg.link(href=self_url, rel="self")
    fg.lastBuildDate(utc_now())
    for item in sorted(items, key=item_sort_key, reverse=True):
        entry = fg.add_entry(order="append")
        entry.id(item.uid)
        entry.title(item.title)
        entry.link(href=item.link)
        entry.description(item.description or f"Source : {item.source}")
        entry.author({"name": item.source})
        published = parse_date_for_feed(item.published or item.first_seen)
        if published:
            entry.pubDate(published)
    output.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(output), pretty=True)


def write_opml(statuses: list[dict[str, Any]], base_url: str) -> None:
    outlines = []
    for st in statuses:
        if st.get("feed"):
            title = html.escape(st["site"], quote=True)
            xml_url = html.escape(urljoin(base_url, st["feed"]), quote=True)
            page_url = html.escape(st.get("url", ""), quote=True)
            outlines.append(f'    <outline type="rss" text="{title}" title="{title}" xmlUrl="{xml_url}" htmlUrl="{page_url}"/>')
    content = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">',
        '  <head><title>Veille RSS</title></head>', '  <body>', *outlines, '  </body>', '</opml>', ''
    ])
    (PUBLIC_DIR / "feeds.opml").write_text(content, encoding="utf-8")


def write_dashboard(payload: dict[str, Any], title: str) -> None:
    rows = []
    for site in payload["sites"]:
        ok = site["status"] == "ok"
        state = "OK" if ok else "ERREUR"
        css = "ok" if ok else "error"
        feed_link = f'<a href="{html.escape(site["feed"])}">Flux RSS</a>' if site.get("feed") else "—"
        error = html.escape(site.get("error", ""))
        details = html.escape(site.get("method", ""))
        if error:
            details = f"{details} — {error}" if details else error
        rows.append(f"<tr><td>{html.escape(site['site'])}</td><td><span class='{css}'>{state}</span></td><td>{site.get('items', 0)}</td><td>{html.escape(details)}</td><td>{feed_link}</td></tr>")
    generated = html.escape(payload["generated_at"])
    page = f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font-family:Arial,sans-serif;max-width:1150px;margin:40px auto;padding:0 20px;color:#1f2937}}h1{{margin-bottom:6px}}.meta{{color:#6b7280;margin-bottom:24px}}.cards{{display:flex;gap:14px;flex-wrap:wrap;margin:20px 0}}.card{{border:1px solid #ddd;border-radius:10px;padding:14px 18px;min-width:150px}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #ddd;text-align:left;padding:12px 8px;vertical-align:top}}th{{background:#f7f7f7}}.ok{{color:#087830;font-weight:bold}}.error{{color:#b42318;font-weight:bold}}a{{color:#075e9e}}code{{background:#f3f4f6;padding:2px 5px;border-radius:4px}}@media(max-width:700px){{table{{font-size:13px}}}}
</style></head><body><h1>{html.escape(title)}</h1><div class="meta">Dernière génération : {generated}</div>
<div class="cards"><div class="card"><strong>{payload['sites_total']}</strong><br>sources</div><div class="card"><strong>{payload['sites_ok']}</strong><br>opérationnelles</div><div class="card"><strong>{payload['sites_error']}</strong><br>en erreur</div><div class="card"><strong>{payload['merged_items']}</strong><br>articles consolidés</div><div class="card"><strong>{payload['new_items']}</strong><br>nouveaux articles</div></div>
<p><a href="veille.xml"><strong>Flux global veille.xml</strong></a> · <a href="feeds.opml">Exporter tous les flux (OPML)</a> · <a href="status.json">État JSON</a></p>
<table><thead><tr><th>Source</th><th>État</th><th>Articles</th><th>Méthode / détail</th><th>Flux</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>'''
    (PUBLIC_DIR / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    cfg = load_config()
    settings = cfg.get("settings") or {}
    sites = cfg["sites"]
    timeout = int(settings.get("request_timeout", 30))
    max_items = int(settings.get("max_items_per_feed", 60))
    history_limit = int(settings.get("max_history_items", 1000))
    keep_previous = bool(settings.get("keep_previous_on_error", True))
    base_url = "https://abonnementsgrp.github.io/veille-rss/"
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    history = load_history()
    session = request_session(settings)
    statuses: list[dict[str, Any]] = []
    all_items: list[Item] = []
    new_count = 0

    for site in sites:
        source = site["name"]
        output_name = site.get("output") or re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-") + ".xml"
        feed_url = ""
        try:
            feed_url = site.get("official_feed") or discover_feed(session, site["url"], timeout) or ""
            if feed_url:
                response = session.get(feed_url, timeout=timeout, allow_redirects=True)
                response.raise_for_status()
                items = parse_feed_bytes(response.content, source, max_items)
                method = "flux officiel" if site.get("official_feed") else "flux détecté"
            else:
                items, method = scrape_page(session, site, timeout, max_items)
            if not items:
                raise RuntimeError("Aucun article détecté sur la page")
            seen_at = utc_now().isoformat()
            for item in items:
                if not item.first_seen:
                    item.first_seen = seen_at
                if item.uid not in history:
                    new_count += 1
                    history[item.uid] = {**asdict(item), "uid": item.uid, "first_seen": seen_at}
                else:
                    item.first_seen = history[item.uid].get("first_seen", seen_at)
                    history[item.uid].update({**asdict(item), "uid": item.uid})
            source_items = dedupe(items + history_items_for_source(history, source, max_items))[:max_items]
            write_feed(source_items, source, f"Actualités de {source}", PUBLIC_DIR / output_name, site["url"], urljoin(base_url, output_name))
            all_items.extend(source_items)
            statuses.append({"site": source, "url": site["url"], "status": "ok", "method": method, "items": len(source_items), "feed": output_name, "source_feed": feed_url})
            log.info("%s : %d article(s) via %s", source, len(source_items), method)
        except Exception as exc:
            previous = history_items_for_source(history, source, max_items) if keep_previous else []
            if previous:
                write_feed(previous, source, f"Actualités de {source}", PUBLIC_DIR / output_name, site["url"], urljoin(base_url, output_name))
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
        base_url,
        urljoin(base_url, merged_output),
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
    write_opml(statuses, base_url)
    write_dashboard(payload, settings.get("site_title", "Tableau de bord de la veille RSS"))
    log.info("Bilan : %d source(s), %d OK, %d erreur(s), %d article(s)", payload["sites_total"], payload["sites_ok"], payload["sites_error"], payload["merged_items"])
    return 0

if __name__ == "__main__":
    sys.exit(main())
