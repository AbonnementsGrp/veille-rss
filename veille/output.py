"""Écriture des sorties publiées : flux XML, OPML, tableau de bord HTML."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from feedgen.feed import FeedGenerator

from veille.config import PUBLIC_DIR
from veille.dates import item_sort_key, parse_date_for_feed, utc_now
from veille.models import Item

DASHBOARD_STYLE = (
    "body{font-family:Arial,sans-serif;max-width:1150px;margin:40px auto;padding:0 20px;color:#1f2937}"
    "h1{margin-bottom:6px}.meta{color:#6b7280;margin-bottom:24px}"
    ".cards{display:flex;gap:14px;flex-wrap:wrap;margin:20px 0}"
    ".card{border:1px solid #ddd;border-radius:10px;padding:14px 18px;min-width:150px}"
    "table{border-collapse:collapse;width:100%}"
    "th,td{border-bottom:1px solid #ddd;text-align:left;padding:12px 8px;vertical-align:top}"
    "th{background:#f7f7f7}.ok{color:#087830;font-weight:bold}.error{color:#b42318;font-weight:bold}"
    "a{color:#075e9e}code{background:#f3f4f6;padding:2px 5px;border-radius:4px}"
    "@media(max-width:700px){table{font-size:13px}}"
)


def write_feed(items: list[Item], title: str, description: str, output: Path, home_url: str, self_url: str = "") -> None:
    """Écrit un flux RSS 2.0, articles triés du plus récent au plus ancien.

    `lastBuildDate` porte la date du plus récent article, et non l'heure de
    génération : la spec RSS la définit comme la dernière fois que le contenu
    du canal a changé. Un flux inchangé produit ainsi un fichier identique,
    ce qui évite un commit toutes les trois heures pour rien.
    """
    fg = FeedGenerator()
    fg.id(home_url)
    fg.title(title)
    fg.description(description)
    fg.language("fr")
    fg.link(href=home_url, rel="alternate")
    if self_url:
        fg.link(href=self_url, rel="self")
    tries = sorted(items, key=item_sort_key, reverse=True)
    fg.lastBuildDate(item_sort_key(tries[0]) if tries else utc_now())
    for item in tries:
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


def write_opml(statuses: list[dict[str, Any]], base_url: str, public_dir: Path | None = None) -> None:
    """Écrit un OPML importable dans un lecteur de flux.

    Seules les sources ayant réellement produit un fichier sont listées : un
    flux annoncé mais absent casse l'import côté lecteur.
    """
    public_dir = public_dir or PUBLIC_DIR
    outlines = []
    for st in statuses:
        if st.get("feed") and (public_dir / st["feed"]).exists():
            title = html.escape(st["site"], quote=True)
            xml_url = html.escape(urljoin(base_url, st["feed"]), quote=True)
            page_url = html.escape(st.get("url", ""), quote=True)
            outlines.append(f'    <outline type="rss" text="{title}" title="{title}" xmlUrl="{xml_url}" htmlUrl="{page_url}"/>')
    content = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">',
        '  <head><title>Veille RSS</title></head>', '  <body>', *outlines, '  </body>', '</opml>', ''
    ])
    (public_dir / "feeds.opml").write_text(content, encoding="utf-8")


def write_dashboard(payload: dict[str, Any], title: str, public_dir: Path | None = None) -> None:
    """Écrit le tableau de bord d'état des sources."""
    public_dir = public_dir or PUBLIC_DIR
    rows = []
    for site in payload["sites"]:
        ok = site["status"] == "ok"
        state = "OK" if ok else "ERREUR"
        css = "ok" if ok else "error"
        has_feed = bool(site.get("feed")) and (public_dir / site["feed"]).exists()
        feed_link = f'<a href="{html.escape(site["feed"])}">Flux RSS</a>' if has_feed else "—"
        error = html.escape(site.get("error", ""))
        details = html.escape(site.get("method", ""))
        if error:
            details = f"{details} — {error}" if details else error
        rows.append(
            f"<tr><td>{html.escape(site['site'])}</td>"
            f"<td><span class='{css}'>{state}</span></td>"
            f"<td>{site.get('items', 0)}</td>"
            f"<td>{details}</td>"
            f"<td>{feed_link}</td></tr>"
        )
    generated = html.escape(payload["generated_at"])
    cards = "".join(
        f'<div class="card"><strong>{payload[key]}</strong><br>{label}</div>'
        for key, label in (
            ("sites_total", "sources"),
            ("sites_ok", "opérationnelles"),
            ("sites_error", "en erreur"),
            ("merged_items", "articles consolidés"),
            ("new_items", "nouveaux articles"),
        )
    )
    page = f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
{DASHBOARD_STYLE}
</style></head><body><h1>{html.escape(title)}</h1><div class="meta">Dernière génération : {generated}</div>
<div class="cards">{cards}</div>
<p><a href="veille.xml"><strong>Flux global veille.xml</strong></a> · <a href="feeds.opml">Exporter tous les flux (OPML)</a> · <a href="status.json">État JSON</a></p>
<table><thead><tr><th>Source</th><th>État</th><th>Articles</th><th>Méthode / détail</th><th>Flux</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>'''
    (public_dir / "index.html").write_text(page, encoding="utf-8")
