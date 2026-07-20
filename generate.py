from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
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

    @property
    def uid(self) -> str:
        raw = f"{self.source}|{self.link}|{self.title}".encode("utf-8", errors="ignore")
        return hashlib.sha256(raw).hexdigest()


def now_rfc2822() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def normalize_date(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return ""
        try:
            dt = parsedate_to_datetime(text)
        except Exception:
            dt = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S%z"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def clean_text(value: str | None, limit: int = 1200) -> str:
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_history() -> dict[str, dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.warning("Historique illisible : démarrage avec un historique vide.")
        return {}


def save_history(history: dict[str, dict[str, Any]], limit: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = list(history.values())
    records.sort(key=lambda x: x.get("first_seen", ""), reverse=True)
    trimmed = {r["uid"]: r for r in records[:limit]}
    HISTORY_PATH.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def session_for(settings: dict[str, Any]) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": settings.get("user_agent", "VeilleRSS/2.0"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
    })
    return s


def discover_feed(session: requests.Session, url: str, timeout: int) -> str | None:
    try:
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    for link in soup.select('link[rel="alternate"]'):
        typ = (link.get("type") or "").lower()
        href = link.get("href")
        if href and any(x in typ for x in ("rss", "atom", "xml")):
            return urljoin(url, href)
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [
        url.rstrip("/") + "/feed/",
        base + "/feed/",
        base + "/rss.xml",
        base + "/feed.xml",
        base + "/atom.xml",
    ]
    for candidate in candidates:
        try:
            rr = session.get(candidate, timeout=timeout)
            if rr.ok and ("xml" in rr.headers.get("content-type", "").lower() or "<rss" in rr.text[:500].lower() or "<feed" in rr.text[:500].lower()):
                parsed_feed = feedparser.parse(rr.content)
                if parsed_feed.entries:
                    return candidate
        except Exception:
            continue
    return None


def parse_official_feed(session: requests.Session, feed_url: str, source: str, timeout: int, max_items: int) -> list[Item]:
    r = session.get(feed_url, timeout=timeout)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    items: list[Item] = []
    for entry in feed.entries[:max_items]:
        title = clean_text(entry.get("title"))
        link = entry.get("link") or ""
        if not title or not link:
            continue
        description = clean_text(entry.get("summary") or entry.get("description"))
        published = normalize_date(entry.get("published") or entry.get("updated"))
        items.append(Item(source=source, title=title, link=link, description=description, published=published))
    return items


def first_match(node: Any, selectors: Iterable[str]) -> Any | None:
    for selector in selectors:
        try:
            found = node.select_one(selector)
            if found:
                return found
        except Exception:
            continue
    return None


def parse_json_ld(soup: BeautifulSoup, source: str, base_url: str, max_items: int) -> list[Item]:
    items: list[Item] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, list):
                stack.extend(obj)
                continue
            if not isinstance(obj, dict):
                continue
            graph = obj.get("@graph")
            if graph:
                stack.append(graph)
            typ = obj.get("@type")
            if isinstance(typ, list):
                typ = " ".join(typ)
            if typ and any(t in str(typ).lower() for t in ("article", "newsarticle", "blogposting")):
                title = clean_text(obj.get("headline") or obj.get("name"))
                link = obj.get("url") or obj.get("mainEntityOfPage")
                if isinstance(link, dict):
                    link = link.get("@id") or link.get("url")
                if title and link:
                    items.append(Item(
                        source=source,
                        title=title,
                        link=urljoin(base_url, str(link)),
                        description=clean_text(obj.get("description")),
                        published=normalize_date(obj.get("datePublished") or obj.get("dateModified")),
                    ))
            if len(items) >= max_items:
                return dedupe(items)
    return dedupe(items)


def scrape_html(session: requests.Session, site: dict[str, Any], timeout: int, max_items: int) -> list[Item]:
    url = site["url"]
    source = site["name"]
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    structured = parse_json_ld(soup, source, url, max_items)
    selectors = site.get("selectors", {})
    item_selectors = selectors.get("item") or ["article", ".post", ".news-item", ".card", "li"]
    title_selectors = selectors.get("title") or ["h1 a", "h2 a", "h3 a", ".entry-title a", "a"]
    desc_selectors = selectors.get("description") or [".excerpt", ".summary", ".entry-summary", "p"]
    date_selectors = selectors.get("date") or ["time", ".date", ".published"]

    nodes: list[Any] = []
    for selector in item_selectors:
        try:
            found = soup.select(selector)
        except Exception:
            continue
        if len(found) >= 2:
            nodes = found
            break

    items: list[Item] = structured[:]
    for node in nodes:
        title_node = first_match(node, title_selectors)
        if not title_node:
            continue
        link_node = title_node if title_node.name == "a" else title_node.find("a")
        href = link_node.get("href") if link_node else None
        title = clean_text(title_node.get_text(" ", strip=True))
        if not href or not title or len(title) < 4:
            continue
        link = urljoin(url, href)
        if urlparse(link).netloc != urlparse(url).netloc:
            continue
        desc_node = first_match(node, desc_selectors)
        date_node = first_match(node, date_selectors)
        date_raw = ""
        if date_node:
            date_raw = date_node.get("datetime") or date_node.get_text(" ", strip=True)
        items.append(Item(
            source=source,
            title=title,
            link=link,
            description=clean_text(desc_node.get_text(" ", strip=True) if desc_node else ""),
            published=normalize_date(date_raw),
        ))
        if len(items) >= max_items * 2:
            break
    return dedupe(items)[:max_items]


def dedupe(items: list[Item]) -> list[Item]:
    seen: set[str] = set()
    result: list[Item] = []
    for item in items:
        key = item.link.rstrip("/") or item.uid
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def write_feed(items: list[Item], title: str, description: str, output: Path, feed_link: str = "") -> None:
    fg = FeedGenerator()
    fg.id(feed_link or title)
    fg.title(title)
    fg.description(description)
    fg.language("fr")
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.link(href=feed_link or "https://github.com/AbonnementsGrp/veille-rss", rel="alternate")
    for item in items:
        fe = fg.add_entry(order="append")
        fe.id(item.uid)
        fe.title(item.title)
        fe.link(href=item.link)
        fe.description(item.description or f"Source : {item.source}")
        fe.author({"name": item.source})
        if item.published:
            try:
                fe.pubDate(parsedate_to_datetime(item.published))
            except Exception:
                pass
    output.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(output), pretty=True)


def main() -> int:
    cfg = load_config()
    settings = cfg.get("settings", {})
    sites = cfg.get("sites", [])
    timeout = int(settings.get("request_timeout", 25))
    max_items = int(settings.get("max_items_per_feed", 50))
    history_limit = int(settings.get("max_history_items", 500))
    session = session_for(settings)
    history = load_history()
    all_items: list[Item] = []
    status: list[dict[str, Any]] = []
    new_count = 0

    for site in sites:
        source = site["name"]
        output_name = site.get("output") or re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-") + ".xml"
        try:
            feed_url = site.get("official_feed") or discover_feed(session, site["url"], timeout)
            if feed_url:
                items = parse_official_feed(session, feed_url, source, timeout, max_items)
                method = "official_feed"
            else:
                items = scrape_html(session, site, timeout, max_items)
                method = "html_scraping"
            if not items:
                raise RuntimeError("Aucun article détecté")
            write_feed(items, source, f"Actualités de {source}", PUBLIC_DIR / output_name, site["url"])
            all_items.extend(items)
            for item in items:
                if item.uid not in history:
                    new_count += 1
                    history[item.uid] = {**asdict(item), "uid": item.uid, "first_seen": datetime.now(timezone.utc).isoformat()}
            status.append({"site": source, "status": "ok", "method": method, "items": len(items), "feed": output_name})
            log.info("%s : %s article(s) via %s", source, len(items), method)
        except Exception as exc:
            status.append({"site": source, "status": "error", "error": str(exc), "feed": output_name})
            log.error("%s : %s", source, exc)

    merged = dedupe(all_items)
    merged.sort(key=lambda x: x.published or "", reverse=True)
    merged = merged[:history_limit]
    merged_title = settings.get("merged_feed_name", "Veille RSS globale")
    merged_description = settings.get("merged_feed_description", "Flux consolidé")
    merged_output = settings.get("merged_output", "veille.xml")
    write_feed(merged, merged_title, merged_description, PUBLIC_DIR / merged_output)
    save_history(history, history_limit)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sites_total": len(sites),
        "sites_ok": sum(1 for s in status if s["status"] == "ok"),
        "sites_error": sum(1 for s in status if s["status"] == "error"),
        "new_items": new_count,
        "merged_items": len(merged),
        "sites": status,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    errors = sum(1 for s in status if s["status"] == "error")
    log.info("Bilan : %s site(s), %s erreur(s), %s nouvel/nouveaux article(s)", len(sites), errors, new_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
