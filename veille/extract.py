"""Extraction d'articles depuis une page HTML, quand aucun flux n'existe.

Trois stratégies sont appliquées dans cet ordre de fiabilité décroissante :
JSON-LD déclaré par le site, sélecteurs CSS (par défaut ou configurés dans
`config/sites.yml`), puis notation des liens de la page.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from veille.dates import normalize_date
from veille.models import Item, dedupe
from veille.text import clean_text

DEFAULT_ITEM_SELECTORS = ["article", ".views-row", ".news-item", ".post", ".card", ".item"]
DEFAULT_TITLE_SELECTORS = ["h1 a", "h2 a", "h3 a", ".title a", ".entry-title a"]
DEFAULT_DESC_SELECTORS = [".excerpt", ".summary", ".entry-summary", ".description", "p"]
DEFAULT_DATE_SELECTORS = ["time", ".date", ".published", "[datetime]"]

# Liens à écarter : navigation, mentions légales, réseaux sociaux.
LINK_BLOCKLIST = (
    "connexion", "contact", "mentions-legales", "politique-de-confidentialite",
    "cookie", "facebook", "linkedin", "instagram", "twitter",
)
LINK_TOPIC_HINTS = ("actualit", "news", "article", "publication", "communique", "blog")
MIN_LINK_SCORE = 5

# Liens de navigation d'un site : rubriques, mots-clés, auteurs, pagination.
# Ils cohabitent avec les articles dans la même liste et ressemblent à des
# titres. Attention : rel="bookmark" désigne au contraire le lien permanent
# d'un article WordPress, il ne doit pas être écarté.
NAV_RELS = frozenset({"category", "tag", "author", "next", "prev", "search"})
NAV_CLASSES = frozenset({"next", "prev", "previous", "page-numbers", "pagination"})
TAXONOMY_PATHS = ("/category/", "/categorie/", "/rubrique/", "/tag/", "/etiquette/", "/author/", "/auteur/")
PAGINATION_PATH = re.compile(r"/page/\d+|[?&]paged?=\d+")

# Dates lisibles dans le texte d'un bloc, quand le site n'emploie ni <time> ni
# attribut datetime : "Publication publiée : 25 juin 2026", "le 03/02/2026".
MOIS_FR = ("janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre"
           "|janv|f[ée]vr|avr|juil|sept|d[ée]c")
DATE_EN_CLAIR = re.compile(rf"(?<!\d)(\d{{1,2}})\s*(?:er)?\s+({MOIS_FR})\.?\s+(\d{{4}})(?!\d)", re.IGNORECASE)
DATE_NUMERIQUE = re.compile(r"(?<!\d)(\d{1,2}[/.]\d{1,2}[/.]\d{4})(?!\d)")


def date_from_text(text: str) -> str:
    """Cherche une date en clair dans un texte et la normalise.

    Le repérage est délibérément étroit : on ne soumet au parseur que la
    portion qui ressemble à une date, jamais le bloc entier, pour ne pas
    ramasser un nombre quelconque de la page.
    """
    if not text:
        return ""
    trouve = DATE_EN_CLAIR.search(text)
    if trouve:
        jour, mois, annee = trouve.groups()
        return normalize_date(f"{jour} {mois} {annee}")
    trouve = DATE_NUMERIQUE.search(text)
    if trouve:
        return normalize_date(trouve.group(1).replace(".", "/"))
    return ""


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
    item_selectors = selectors.get("item") or DEFAULT_ITEM_SELECTORS
    title_selectors = selectors.get("title") or DEFAULT_TITLE_SELECTORS
    desc_selectors = selectors.get("description") or DEFAULT_DESC_SELECTORS
    date_selectors = selectors.get("date") or DEFAULT_DATE_SELECTORS
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
        published = normalize_date(raw_date) or date_from_text(node.get_text(" ", strip=True))
        items.append(Item(
            source=site["name"],
            title=title,
            link=urljoin(site["url"], anchor["href"]),
            description=clean_text(desc_node.get_text(" ", strip=True) if desc_node else ""),
            published=published,
        ))
        if len(items) >= max_items:
            break
    return dedupe(items)


def generic_link_score(anchor: Any, base_host: str, patterns: list[str]) -> int:
    """Note la probabilité qu'un lien pointe vers un article. Négative = rejet."""
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
    if any(x in low for x in LINK_BLOCKLIST):
        return -100
    if {r.lower() for r in (anchor.get("rel") or [])} & NAV_RELS:
        return -100
    if {c.lower() for c in (anchor.get("class") or [])} & NAV_CLASSES:
        return -100
    low_href = href.lower()
    if any(t in low_href for t in TAXONOMY_PATHS) or PAGINATION_PATH.search(low_href):
        return -100
    score = 0
    if anchor.find_parent(["article", "main"]): score += 4
    if anchor.find_parent(["h1", "h2", "h3", "h4"]): score += 5
    if any(p.lower() in href.lower() for p in patterns): score += 8
    if any(x in href.lower() for x in LINK_TOPIC_HINTS): score += 5
    if re.search(r"/20\d{2}/|\d{4}-\d{2}-\d{2}", href): score += 3
    if len(text) >= 25: score += 2
    return score


def extract_generic_links(soup: BeautifulSoup, site: dict[str, Any], max_items: int) -> list[Item]:
    base = urlparse(site["url"])
    patterns = site.get("link_patterns") or []
    ranked: list[tuple[int, Item]] = []
    for anchor in soup.select("a[href]"):
        score = generic_link_score(anchor, base.netloc, patterns)
        if score < MIN_LINK_SCORE:
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
            if not published:
                published = date_from_text(container.get_text(" ", strip=True))
        ranked.append((score, Item(site["name"], title, href, description, published)))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return dedupe([item for _, item in ranked])[:max_items]


def scrape_page(session: requests.Session, site: dict[str, Any], timeout: int, max_items: int) -> tuple[list[Item], str]:
    """Extrait les articles d'une page et rend la méthode qui a abouti."""
    response = session.get(site["url"], timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    site = {**site, "url": response.url}

    # Le JSON-LD se lit avant tout nettoyage : il vit dans une balise <script>,
    # que le retrait du bruit ci-dessous supprimerait.
    json_items = parse_json_ld(soup, site["name"], response.url, max_items)
    for selector in ("script", "style", "noscript", "svg"):
        for node in soup.select(selector):
            node.decompose()
    selector_items = extract_with_selectors(soup, site, max_items)

    # Les données structurées et les sélecteurs désignent des articles ; ils se
    # complètent sans se contredire. La notation des liens, elle, ratisse toute
    # la page : elle ne sert que si les deux premières n'ont rien donné, sinon
    # elle rajoute au résultat le lien de FAQ ou d'agenda du bandeau latéral.
    identifies = dedupe(json_items + selector_items)
    if identifies:
        method = "json_ld+html" if json_items else "html_selectors"
        return identifies[:max_items], method
    return extract_generic_links(soup, site, max_items)[:max_items], "generic_links"
