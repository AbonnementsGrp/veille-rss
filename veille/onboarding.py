"""Enquête sur une page d'actualités en vue d'en faire une source.

Ajouter une source demandait de savoir tester un flux, choisir un mode, parfois
écrire des sélecteurs. Ce module fait cette enquête à partir de la seule URL :
il cherche le flux, extrait les articles, propose un nom, et rend un verdict
honnête — y compris « cette source demande un réglage manuel » quand la page ne
se laisse pas lire. Le bloc de configuration devient un détail que personne n'a
à écrire à la main.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup

from veille.config import CONFIG_PATH, load_config, theme_of
from veille.extract import scrape_page
from veille.feeds import discover_feed
from veille.models import Item
from veille.pipeline import output_name_for, read_feed
from veille.text import clean_text

# En deçà, l'enquête n'a probablement pas trouvé la liste d'articles.
MIN_ARTICLES = 3
# Part d'articles datés en deçà de laquelle le résultat mérite vérification.
MIN_DATED_RATIO = 0.5
PREVIEW_SIZE = 5

VERDICT_OK = "ok"
VERDICT_A_VERIFIER = "a_verifier"
VERDICT_MANUEL = "manuel"

# Séparateurs usuels d'un <title> : "Actualités | Site", "Actualités - Site".
TITLE_SEPARATORS = re.compile(r"\s+[|–—\-:·»]\s+")
# Mots qui désignent une rubrique et non le site lui-même.
RUBRIQUE_WORDS = {"actualités", "actualites", "actus", "news", "accueil", "home", "blog"}


@dataclass
class Proposal:
    """Résultat de l'enquête : ce qui serait écrit, et de quoi en juger."""

    url: str
    name: str
    short_name: str
    theme: str
    output: str
    official_feed: str
    method: str
    items: list[Item]
    verdict: str
    warnings: list[str] = field(default_factory=list)
    render: bool = False

    def to_site(self) -> dict[str, Any]:
        """Le bloc de configuration, tel qu'il figurerait dans sites.yml."""
        site: dict[str, Any] = {"name": self.name}
        if self.short_name and self.short_name != self.name:
            site["short_name"] = self.short_name
        if self.theme:
            site["theme"] = self.theme
        site["url"] = self.url
        if self.official_feed:
            site["official_feed"] = self.official_feed
        site["output"] = self.output
        if self.render:
            site["mode"] = "page"
            site["render"] = True
        return site


def site_name_from_html(html: str) -> str:
    """Propose un nom de source à partir des métadonnées de la page.

    `og:site_name` désigne le site ; à défaut le <title>, dont on écarte le
    segment qui ne fait que nommer la rubrique ("Actualités - Mon site").
    """
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one('meta[property="og:site_name"]')
    if meta and meta.get("content"):
        return clean_text(meta["content"], 120)
    titre = clean_text(soup.title.get_text() if soup.title else "", 200)
    if not titre:
        return ""
    segments = [s for s in TITLE_SEPARATORS.split(titre) if s.strip()]
    utiles = [s for s in segments if s.strip().lower() not in RUBRIQUE_WORDS]
    return (utiles or segments)[-1].strip() if len(segments) > 1 else titre


def juger(items: list[Item], method: str) -> tuple[str, list[str]]:
    """Rend le verdict et les réserves qui l'accompagnent."""
    if not items:
        return VERDICT_MANUEL, ["aucun article détecté : la page est peut-être rendue en JavaScript, "
                                "ou sa structure demande des sélecteurs écrits à la main"]
    reserves: list[str] = []
    if len(items) < MIN_ARTICLES:
        reserves.append(f"seulement {len(items)} article(s) trouvé(s)")
    dates = sum(1 for i in items if i.published)
    if dates / len(items) < MIN_DATED_RATIO:
        reserves.append(f"{len(items) - dates} article(s) sur {len(items)} sans date : "
                        "ils seront datés du jour de leur découverte")
    if method.endswith("generic_links"):
        reserves.append("articles trouvés par notation des liens, la méthode la moins fiable : "
                        "vérifier qu'il ne s'agit pas de liens de navigation")
    if method.startswith("navigateur"):
        reserves.append("page rendue en JavaScript : les articles n'apparaissent qu'à travers le navigateur "
                        "sans tête, la collecte sera plus lente ; vérifier les titres proposés")
    return (VERDICT_A_VERIFIER if reserves else VERDICT_OK), reserves


def already_followed(url: str, sites: list[dict[str, Any]]) -> str:
    """Rend le nom de la source qui suit déjà cette URL, ou ""."""
    cible = url.rstrip("/").lower()
    for site in sites:
        for cle in ("url", "official_feed"):
            if str(site.get(cle, "")).rstrip("/").lower() == cible:
                return site["name"]
    return ""


def unique_output(base: str, sites: list[dict[str, Any]]) -> str:
    pris = {str(s.get("output") or output_name_for(s)) for s in sites}
    if base not in pris:
        return base
    racine = base[:-4] if base.endswith(".xml") else base
    n = 2
    while f"{racine}-{n}.xml" in pris:
        n += 1
    return f"{racine}-{n}.xml"


def investigate(session: Any, url: str, *, name: str = "", short_name: str = "", theme: str = "",
                timeout: int = 30, max_items: int = 60,
                cfg: dict[str, Any] | None = None, browser: Any = None) -> Proposal:
    """Enquête sur une URL et propose une configuration complète.

    `browser` est un navigateur sans tête facultatif : quand la page ne livre
    aucun article à la session HTTP, l'enquête la rend en JavaScript et, si
    des articles apparaissent alors, propose `render: true`.
    """
    cfg = cfg or load_config()
    sites = cfg["sites"]
    themes = [str(t) for t in ((cfg.get("settings") or {}).get("themes") or [])]
    warnings: list[str] = []

    deja = already_followed(url, sites)
    if deja:
        warnings.append(f"cette adresse est déjà suivie par la source « {deja} »")

    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    url = response.url
    nom_propose = site_name_from_html(response.text)

    feed = discover_feed(session, url, timeout) or ""
    if feed:
        items = read_feed(session, feed, name or nom_propose or url, timeout, max_items)
        method = "flux détecté"
    else:
        items, method = scrape_page(session, {"name": name or nom_propose or url, "url": url}, timeout, max_items)

    render = False
    if not items and browser is not None:
        try:
            items, method = scrape_page(browser, {"name": name or nom_propose or url, "url": url}, timeout, max_items)
        except Exception as exc:
            warnings.append(f"rendu par navigateur impossible : {exc}")
        if items:
            render = True
            method = f"navigateur : {method}"

    verdict, reserves = juger(items, method)
    warnings.extend(reserves)
    if deja and verdict == VERDICT_OK:
        # Un doublon n'est pas une erreur technique, mais l'approbateur doit s'arrêter dessus.
        verdict = VERDICT_A_VERIFIER
    if theme and themes and theme not in themes:
        warnings.append(f"le domaine « {theme} » n'existe pas encore : la source apparaîtra sous "
                        "« Autres ». Pour le créer, utiliser le formulaire « Proposer un nouveau domaine »")

    nom = (name or nom_propose or url).strip()
    court = (short_name or nom).strip()
    for item in items:
        item.source = nom
    return Proposal(
        url=url, name=nom, short_name=court, theme=theme,
        output=unique_output(output_name_for({"name": nom}), sites),
        official_feed=feed, method=method, items=items[:PREVIEW_SIZE],
        verdict=verdict, warnings=warnings, render=render,
    )


def render_block(site: dict[str, Any]) -> str:
    """Écrit un bloc de source dans le style du fichier : une clé par ligne, entre guillemets."""
    lignes = []
    for n, (cle, valeur) in enumerate(site.items()):
        prefixe = "  - " if n == 0 else "    "
        if isinstance(valeur, bool):
            rendu = "true" if valeur else "false"
        else:
            rendu = f'"{str(valeur).replace(chr(34), chr(39))}"'
        lignes.append(f"{prefixe}{cle}: {rendu}")
    return "\n".join(lignes) + "\n"


def append_site(site: dict[str, Any], path: Path | None = None) -> None:
    """Ajoute une source en fin de fichier, sans réécrire le reste.

    Le fichier n'est pas repassé par le sérialiseur YAML : cela effacerait ses
    commentaires. Le bloc est ajouté tel quel, puis le résultat est relu pour
    vérifier qu'il reste valide et que la source ne fait pas doublon.
    """
    path = path or CONFIG_PATH
    texte = path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(texte) or {}
    sites = cfg.get("sites") or []
    if any(s.get("name") == site["name"] for s in sites):
        raise ValueError(f"une source nommée « {site['name']} » existe déjà")
    if any(str(s.get("output") or output_name_for(s)) == site["output"] for s in sites):
        raise ValueError(f"le fichier de sortie {site['output']} est déjà utilisé")
    if not list(cfg.keys())[-1:] == ["sites"]:
        raise ValueError("la section 'sites' doit être la dernière du fichier pour un ajout en fin")

    nouveau = texte.rstrip("\n") + "\n\n" + render_block(site)
    relu = yaml.safe_load(nouveau)
    if len(relu.get("sites") or []) != len(sites) + 1:
        raise ValueError("le fichier ne relit pas correctement après ajout")
    path.write_text(nouveau, encoding="utf-8")


__all__ = [
    "Proposal", "VERDICT_A_VERIFIER", "VERDICT_MANUEL", "VERDICT_OK",
    "append_site", "investigate", "juger", "render_block", "site_name_from_html", "theme_of",
]
