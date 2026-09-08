"""Écriture des sorties publiées : flux XML, OPML, tableau de bord HTML."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from feedgen.feed import FeedGenerator

from veille.config import AUTRES, PUBLIC_DIR, sort_key
from veille.dates import item_sort_key, parse_date_for_feed, utc_now
from veille.models import Item

# Le planificateur GitHub décale les exécutions, parfois de plusieurs heures.
# Trois créneaux manqués sortent nettement de cette dispersion.
STALE_AFTER_HOURS = 9
# Colonnes du tableau des sources : les intertitres de domaine les enjambent toutes.
COLONNES = 6

# Formulaire d'issue par lequel n'importe qui, sans outillage, propose une source.
PROPOSE_SOURCE_URL = "https://github.com/AbonnementsGrp/veille-rss/issues/new?template=nouvelle-source.yml"
PROPOSE_THEME_URL = "https://github.com/AbonnementsGrp/veille-rss/issues/new?template=nouveau-domaine.yml"
RENAME_THEME_URL = "https://github.com/AbonnementsGrp/veille-rss/issues/new?template=renommer-domaine.yml"
REMOVE_SOURCE_URL = "https://github.com/AbonnementsGrp/veille-rss/issues/new?template=supprimer-source.yml"
REMOVE_THEME_URL = "https://github.com/AbonnementsGrp/veille-rss/issues/new?template=supprimer-domaine.yml"
# Les demandes déposées par formulaire qui attendent un responsable : issues
# ouvertes sans l'étiquette « approuvé ». La page étant statique, leur nombre est
# lu chez GitHub par le navigateur du lecteur (API publique, sans jeton).
PENDING_ISSUES_URL = "https://github.com/AbonnementsGrp/veille-rss/issues?q=is%3Aissue+is%3Aopen+-label%3Aapprouv%C3%A9"
PENDING_ISSUES_API = "https://api.github.com/repos/AbonnementsGrp/veille-rss/issues?state=open&per_page=100"
APPROVED_LABEL = "approuvé"

DASHBOARD_STYLE = (
    "html{scroll-behavior:smooth}"
    "body{font-family:Arial,sans-serif;max-width:1600px;margin:40px auto;padding:0 20px;color:#1f2937}"
    "h1{margin-bottom:6px}.meta{color:#6b7280;margin-bottom:24px}p.gestion{color:#6b7280}"
    # Bouton « Demandes à valider » : le seul élément saillant de la ligne de
    # gestion, parce qu'il appelle une action d'un responsable.
    "a.bouton{display:inline-block;padding:6px 12px;border-radius:8px;background:#075e9e;color:#fff;"
    "text-decoration:none;font-weight:bold}a.bouton:hover{background:#0b6fb8}"
    ".badge{display:inline-block;min-width:18px;padding:1px 6px;margin-left:6px;border-radius:9px;"
    "background:#fff;color:#075e9e;font-size:12px;text-align:center}"
    "p.demandes .aide{margin-left:10px}"
    # Sommaire des domaines : colonne fixe à gauche sur grand écran, qui reste
    # visible pendant le défilement ; bandeau au-dessus du tableau sur écran étroit.
    ".layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:28px;align-items:start;margin-top:8px}"
    "nav.domaines{position:sticky;top:16px;border:1px solid #ddd;border-radius:10px;padding:12px 14px;background:#fafafa}"
    "nav.domaines h2{margin:0 0 8px;font-size:13px;color:#6b7280;letter-spacing:.04em;text-transform:uppercase}"
    "nav.domaines ul{list-style:none;margin:0;padding:0}nav.domaines li{padding:5px 0;line-height:1.35}"
    "nav.domaines .compte{color:#6b7280;font-size:12px}"
    "nav.domaines li.vide{color:#9ca3af}nav.domaines li.vide span[title]{cursor:help}"
    "tr.theme{scroll-margin-top:12px}tr.theme:target th{background:#fde68a}"
    # Colonne « Flux » : l'adresse tient sur une ligne, quoi qu'il arrive ; si
    # l'écran est trop étroit, c'est le tableau qui défile, pas l'adresse qui se plie.
    ".contenu{overflow-x:auto}td.activite{white-space:nowrap}"
    "a.url{font-family:Consolas,Menlo,monospace;font-size:12px}"
    # Colonne « Méthode / détail » : compacte ; le message brut se déplie d'un clic.
    "td.detail{max-width:230px}td.detail summary{cursor:pointer;color:#b42318}"
    "td.detail .brut{margin-top:6px;font-family:Consolas,Menlo,monospace;font-size:11px;color:#6b7280;"
    "white-space:pre-wrap;word-break:break-all}"
    "button.copier{margin-left:6px;font-size:11px;padding:2px 8px;border:1px solid #cbd5e1;border-radius:6px;"
    "background:#fff;color:#334155;cursor:pointer;vertical-align:middle}"
    "button.copier:hover{background:#f1f5f9}"
    "td.activite .absent{color:#6b7280;font-style:italic}"
    "td.activite .filtre{display:block;color:#6b7280;font-size:11px;margin-top:2px}"
    "@media(max-width:900px){.layout{grid-template-columns:1fr}nav.domaines{position:static}"
    "nav.domaines ul{display:flex;flex-wrap:wrap;gap:6px 16px}}"
    ".cards{display:flex;gap:14px;flex-wrap:wrap;margin:20px 0}"
    ".card{border:1px solid #ddd;border-radius:10px;padding:14px 18px;min-width:150px}"
    "table{border-collapse:collapse;width:100%}"
    "th,td{border-bottom:1px solid #ddd;text-align:left;padding:12px 8px;vertical-align:top}"
    "th{background:#f7f7f7}.ok{color:#087830;font-weight:bold}.error{color:#b42318;font-weight:bold}"
    # « À surveiller » : la source répond, mais quelque chose cloche ; en orange,
    # entre le vert du OK et le rouge de l'erreur.
    ".warn{color:#b45309;font-weight:bold;cursor:help}"
    "td.detail .avert{display:block;color:#b45309;font-size:12px;margin-top:4px}"
    "tr.theme th{background:#eef2f7;color:#334155;font-size:13px;letter-spacing:.04em;text-transform:uppercase;padding-top:18px}"
    "a{color:#075e9e}code{background:#f3f4f6;padding:2px 5px;border-radius:4px}"
    ".stale{background:#fef3c7;border:1px solid #f59e0b;color:#92400e;padding:12px 16px;border-radius:8px;margin:16px 0}"
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

    Les sources sont groupées par domaine : l'import crée un dossier par
    domaine plutôt qu'une liste de onze flux en vrac.

    Seules les sources ayant réellement produit un fichier sont listées : un
    flux annoncé mais absent casse l'import côté lecteur.
    """
    public_dir = public_dir or PUBLIC_DIR
    lignes: list[str] = []
    domaine_courant: str | None = None
    for st in statuses:
        if not st.get("feed") or not (public_dir / st["feed"]).exists():
            continue
        domaine = st.get("theme") or ""
        if domaine != domaine_courant:
            if domaine_courant is not None:
                lignes.append("    </outline>")
            domaine_courant = domaine
            lignes.append(f'    <outline text="{html.escape(domaine or "Veille", quote=True)}" '
                          f'title="{html.escape(domaine or "Veille", quote=True)}">')
        titre = html.escape(st.get("short_name") or st["site"], quote=True)
        xml_url = html.escape(urljoin(base_url, st["feed"]), quote=True)
        page_url = html.escape(st.get("url", ""), quote=True)
        lignes.append(f'      <outline type="rss" text="{titre}" title="{titre}" '
                      f'xmlUrl="{xml_url}" htmlUrl="{page_url}"/>')
    if domaine_courant is not None:
        lignes.append("    </outline>")
    content = '\n'.join([
        '<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">',
        '  <head><title>Veille RSS</title></head>', '  <body>', *lignes, '  </body>', '</opml>', ''
    ])
    (public_dir / "feeds.opml").write_text(content, encoding="utf-8")


# Méthodes pour lesquelles l'adresse de flux enregistrée est réellement celle d'un
# flux qui fonctionne. En repli, l'adresse configurée existe mais ne sert à rien.
NATIVE_FEED_METHODS = frozenset({"flux officiel", "flux détecté"})


def native_feed_url(site: dict[str, Any]) -> str:
    """L'adresse du flux RSS propre au site source, ou "" s'il n'en a pas d'exploitable."""
    if site.get("method") in NATIVE_FEED_METHODS:
        return str(site.get("source_feed") or "")
    return ""


def native_feed_cell(site: dict[str, Any]) -> str:
    """La cellule « Flux » : l'adresse du flux du site, en clair, avec un bouton pour la copier.

    Vocabulaire du tableau : « Flux » est le flux que le site publie lui-même,
    « Activité » le flux que la veille produit pour cette source.

    L'adresse est affichée telle quelle plutôt que derrière un libellé : c'est
    elle que l'on veut copier dans un lecteur de flux, sans passer par un clic
    droit. Les sources sans flux natif — lues sur leur page ou leur plan de site —
    n'ont rien à montrer ici ; leur flux reste celui produit par la veille.
    """
    url = native_feed_url(site)
    if not url:
        return ('<td class="activite"><span title="Ce site ne publie pas de flux exploitable : la veille lit '
                'sa page ou son plan de site. Utiliser le flux de la veille, colonne Activité." class="absent">'
                'pas de flux publié</span></td>')
    echappee = html.escape(url, quote=True)
    categories = [str(c) for c in (site.get("feed_categories") or [])]
    # Un flux général dont la veille ne garde qu'une rubrique : le dire, car qui
    # s'abonne directement à cette adresse recevra tout le site.
    filtre = (f' <span class="filtre" title="La veille ne garde de ce flux que la catégorie indiquée ; '
              f'un abonnement direct reçoit tout le site.">filtré : {html.escape(", ".join(categories))}</span>'
              if categories else "")
    return (f'<td class="activite"><a class="url" href="{echappee}">{echappee}</a>'
            f' <button type="button" class="copier" data-url="{echappee}" title="Copier l\'adresse">Copier</button>'
            f'{filtre}</td>')


# Résumés lisibles des erreurs les plus courantes, du plus spécifique au plus
# général : le premier motif reconnu l'emporte. Le message brut reste consultable.
ERROR_SUMMARIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("certificate_verify_failed", "sslerror", "ssl:"), "certificat TLS du site incomplet"),
    (("ne sert pas un flux",), "le flux annoncé renvoie une page, pas un flux"),
    (("flux rss invalide", "not well-formed"), "flux illisible"),
    (("aucun article",), "aucun article détecté"),
    (("404",), "page introuvable (404)"),
    (("403",), "accès refusé (403)"),
    (("500", "502", "503", "504"), "erreur du serveur distant"),
    (("timed out", "timeout"), "délai de réponse dépassé"),
    (("nameresolution", "getaddrinfo", "name or service not known"), "site injoignable (nom inconnu)"),
    (("connection refused", "max retries exceeded", "connectionerror"), "connexion impossible"),
)
ERROR_EXCERPT = 70


def summarize_error(message: str) -> str:
    """Résume un message d'erreur technique en quelques mots compréhensibles.

    Les messages bruts sont écrits pour des développeurs et tiennent parfois sur
    trois lignes ; la colonne du tableau doit rester lisible d'un coup d'œil.
    Un message inconnu est simplement tronqué.
    """
    bas = message.lower()
    for motifs, resume in ERROR_SUMMARIES:
        if any(m in bas for m in motifs):
            return resume
    message = " ".join(message.split())
    return message if len(message) <= ERROR_EXCERPT else message[:ERROR_EXCERPT - 1].rstrip() + "…"


def detail_cell(site: dict[str, Any]) -> str:
    """La cellule « Méthode / détail » : la méthode, et pour une erreur son résumé.

    Le message complet est replié derrière le résumé — un clic l'ouvre — pour que
    la colonne garde une largeur raisonnable quelle que soit la verbosité de
    l'erreur.
    """
    methode = html.escape(site.get("method", ""))
    erreur = site.get("error", "")
    if not erreur:
        avertissements = "".join(f'<span class="avert">⚠ {html.escape(str(a))}</span>' for a in warnings_of(site))
        return f'<td class="detail">{methode}{avertissements}</td>'
    resume = html.escape(summarize_error(erreur))
    visible = f"{methode} — {resume}" if methode else resume
    return (f'<td class="detail"><details><summary>{visible}</summary>'
            f'<div class="brut">{html.escape(erreur)}</div></details></td>')


def warnings_of(site: dict[str, Any]) -> list[str]:
    """Les avertissements de surveillance d'une source en état OK ; rien pour une erreur."""
    if site.get("status") != "ok":
        return []
    return [str(a) for a in (site.get("warnings") or []) if str(a).strip()]


def source_row(site: dict[str, Any], public_dir: Path) -> str:
    """Rend la ligne du tableau de bord décrivant une source."""
    ok = site["status"] == "ok"
    etat = "OK" if ok else "ERREUR"
    css = "ok" if ok else "error"
    avertissements = warnings_of(site)
    surveiller = ""
    if avertissements:
        infobulle = html.escape("À surveiller : " + " ; ".join(avertissements), quote=True)
        surveiller = f' <span class="warn" title="{infobulle}">⚠</span>'
    a_un_flux = bool(site.get("feed")) and (public_dir / site["feed"]).exists()
    lien_flux = f'<a href="{html.escape(site["feed"])}">Flux RSS</a>' if a_un_flux else "—"
    # Le nom court suffit à l'écran ; le nom complet reste lisible au survol.
    affiche = html.escape(site.get("short_name") or site["site"])
    complet = html.escape(site["site"], quote=True)
    return (
        f'<tr><td><span title="{complet}">{affiche}</span></td>'
        f"<td><span class='{css}'>{etat}</span>{surveiller}</td>"
        f"<td>{site.get('items', 0)}</td>"
        f"{native_feed_cell(site)}"
        f"<td>{lien_flux}</td>"
        f"{detail_cell(site)}</tr>"
    )


def theme_anchor(theme: str) -> str:
    """Identifiant d'ancre d'un domaine : « Santé, social & séniors » → domaine-sante-social-seniors."""
    return "domaine-" + (re.sub(r"[^a-z0-9]+", "-", sort_key(theme)).strip("-") or "sans-nom")


def domain_summary(sites: list[dict[str, Any]]) -> list[tuple[str, int, int, int]]:
    """Pour chaque domaine, dans l'ordre reçu : (nom, sources, en erreur, à surveiller)."""
    resume: list[tuple[str, int, int, int]] = []
    for site in sites:
        domaine = site.get("theme") or ""
        if not domaine:
            continue
        if not resume or resume[-1][0] != domaine:
            resume.append((domaine, 0, 0, 0))
        nom, total, erreurs, surveiller = resume[-1]
        resume[-1] = (nom, total + 1, erreurs + (site.get("status") != "ok"), surveiller + bool(warnings_of(site)))
    return resume


def domain_nav(sites: list[dict[str, Any]], themes: list[str] | None = None) -> str:
    """La liste des domaines qui mène à chaque rubrique du tableau.

    Avec une dizaine de domaines, parcourir le tableau reste possible ; au-delà,
    il faut un sommaire. Chaque entrée donne le nombre de sources du domaine et
    signale s'il en compte une en erreur, pour voir d'un coup d'œil où regarder.
    Un domaine reconnu mais encore sans source y figure aussi, à zéro et sans
    lien : sinon, celui qui vient de le créer le cherche en vain.
    """
    resume = domain_summary(sites)
    presents = {nom for nom, *_ in resume}
    vides = [(t, 0, 0, 0) for t in (themes or []) if t not in presents]
    lignes = sorted(resume + vides, key=lambda e: (e[0] == AUTRES, sort_key(e[0])))
    if not lignes:
        return ""
    entrees = []
    for domaine, total, erreurs, surveiller in lignes:
        # L'erreur prime : un seul signe par domaine, du plus grave.
        if erreurs:
            alerte = f' <span class="error" title="{erreurs} source(s) en erreur">⚠</span>'
        elif surveiller:
            alerte = f' <span class="warn" title="{surveiller} source(s) à surveiller">⚠</span>'
        else:
            alerte = ""
        if total == 0:
            entrees.append(
                f'<li class="vide"><span title="Aucune source pour l\'instant : proposez-en une">'
                f'{html.escape(domaine)}</span> <span class="compte">0</span></li>'
            )
            continue
        entrees.append(
            f'<li><a href="#{theme_anchor(domaine)}">{html.escape(domaine)}</a>'
            f' <span class="compte">{total}</span>{alerte}</li>'
        )
    return f'<nav class="domaines" aria-label="Domaines"><h2>Domaines</h2><ul>{"".join(entrees)}</ul></nav>'


def dashboard_rows(sites: list[dict[str, Any]], public_dir: Path) -> str:
    """Assemble les lignes, séparées par un intertitre à chaque changement de domaine.

    L'ordre reçu est celui du traitement, déjà trié par domaine : le tableau de
    bord suit la configuration plutôt que d'imposer un classement à part. Chaque
    intertitre porte une ancre, cible du sommaire des domaines.
    """
    lignes = []
    domaine_courant = None
    for site in sites:
        domaine = site.get("theme") or ""
        if domaine and domaine != domaine_courant:
            domaine_courant = domaine
            lignes.append(f'<tr class="theme" id="{theme_anchor(domaine)}">'
                          f'<th colspan="{COLONNES}">{html.escape(domaine)}</th></tr>')
        lignes.append(source_row(site, public_dir))
    return "".join(lignes)


def write_dashboard(payload: dict[str, Any], title: str, public_dir: Path | None = None) -> None:
    """Écrit le tableau de bord d'état des sources."""
    public_dir = public_dir or PUBLIC_DIR
    lignes = dashboard_rows(payload["sites"], public_dir)
    sommaire = domain_nav(payload["sites"], [str(t) for t in (payload.get("themes") or [])])
    generated = html.escape(payload["generated_at"])
    cards = "".join(
        f'<div class="card"><strong>{payload.get(key, 0)}</strong><br>{label}</div>'
        for key, label in (
            ("sites_total", "sources"),
            ("sites_ok", "opérationnelles"),
            ("sites_warning", "à surveiller"),
            ("sites_error", "en erreur"),
            ("merged_items", "articles consolidés"),
            ("new_items", "nouveaux articles"),
        )
    )
    page = f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
{DASHBOARD_STYLE}
</style></head><body><h1>{html.escape(title)}</h1><div class="meta">Dernière génération : <time id="generation" datetime="{generated}">{generated}</time><span id="fraicheur"></span></div>
<div id="alerte" hidden class="stale"></div>
<div class="cards">{cards}</div>
<p><a href="veille.xml"><strong>Flux global veille.xml</strong></a> · <a href="feeds.opml">Exporter tous les flux (OPML)</a> · <a href="status.json">État JSON</a></p>
<p class="gestion">Gérer la veille : <a href="{PROPOSE_SOURCE_URL}">Proposer une source</a> · <a href="{REMOVE_SOURCE_URL}">Supprimer une source</a> · <a href="{PROPOSE_THEME_URL}">Proposer un domaine</a> · <a href="{RENAME_THEME_URL}">Renommer un domaine</a> · <a href="{REMOVE_THEME_URL}">Supprimer un domaine</a></p>
<p class="gestion demandes"><a class="bouton" href="{PENDING_ISSUES_URL}">Demandes à valider<span id="nb-demandes" class="badge" hidden></span></a><span class="aide">Les demandes déposées par formulaire attendent qu'un responsable pose l'étiquette « approuvé ».</span></p>
<div class="layout">{sommaire}<div class="contenu">
<table><thead><tr><th>Source</th><th>État</th><th>Articles</th><th>Flux</th><th>Activité</th><th>Méthode / détail</th></tr></thead><tbody>{lignes}</tbody></table>
</div></div>
<script>
// La page est statique : si la génération s'arrête, elle se fige avec sa date.
// Seul le navigateur du lecteur peut donc constater que la veille ne tourne plus.
(function () {{
  var balise = document.getElementById("generation");
  var quand = Date.parse(balise ? balise.getAttribute("datetime") : "");
  if (!quand) return;
  var heures = (Date.now() - quand) / 3600000;
  document.getElementById("fraicheur").textContent = heures < 2
    ? " (il y a moins de deux heures)"
    : " (il y a " + Math.floor(heures) + " heures)";
  if (heures >= {STALE_AFTER_HOURS}) {{
    var alerte = document.getElementById("alerte");
    alerte.textContent = "La veille n'a pas été mise à jour depuis "
      + Math.floor(heures) + " heures, alors qu'elle tourne normalement toutes les trois heures.";
    alerte.appendChild(document.createElement("br"));
    var lien = document.createElement("a");
    lien.href = "https://github.com/AbonnementsGrp/veille-rss/actions";
    lien.textContent = "Voir les exécutions GitHub Actions";
    alerte.appendChild(lien);
    alerte.hidden = false;
  }}
}})();
// Nombre de demandes en attente : lu chez GitHub par le navigateur du lecteur,
// la page étant statique. Sans réponse (hors ligne, quota), le bouton reste tel quel.
(function () {{
  var badge = document.getElementById("nb-demandes");
  if (!badge || !window.fetch) return;
  fetch("{PENDING_ISSUES_API}", {{headers: {{Accept: "application/vnd.github+json"}}}})
    .then(function (reponse) {{ return reponse.ok ? reponse.json() : Promise.reject(); }})
    .then(function (issues) {{
      var attente = issues.filter(function (issue) {{
        return !issue.pull_request && !issue.labels.some(function (l) {{ return l.name === "{APPROVED_LABEL}"; }});
      }}).length;
      badge.textContent = String(attente);
      badge.hidden = false;
    }})
    .catch(function () {{}});
}})();
// Bouton « Copier » de la colonne Activité : l'adresse part dans le presse-papiers.
// Si le navigateur refuse, une boîte de dialogue la présente déjà sélectionnée.
document.addEventListener("click", function (evenement) {{
  var bouton = evenement.target.closest("button.copier");
  if (!bouton) return;
  var adresse = bouton.getAttribute("data-url");
  var confirmer = function () {{
    bouton.textContent = "Copié";
    setTimeout(function () {{ bouton.textContent = "Copier"; }}, 1500);
  }};
  var secours = function () {{ window.prompt("Copiez l'adresse :", adresse); }};
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(adresse).then(confirmer, secours);
  }} else {{
    secours();
  }}
}});
</script>
</body></html>'''
    (public_dir / "index.html").write_text(page, encoding="utf-8")
