"""Rendu d'une page par un navigateur sans tête, pour les sites en JavaScript.

Certains sites (Salesforce Experience Cloud, applications React ou Angular…)
ne livrent à un client HTTP qu'une coquille vide : titres, liens et résumés
n'apparaissent qu'une fois le JavaScript exécuté. `BrowserSession` offre la
même méthode `get()` qu'une session requests, mais rend la page dans Chromium
(via Playwright) et livre le HTML final. Le reste du traitement — JSON-LD,
sélecteurs, notation des liens, lecture des résumés — ignore la différence.

Le HTML livré est « aplati » : les composants web dessinent dans un shadow
DOM que la sérialisation ordinaire ignore (une page Salesforce se résume alors
à quelques balises vides). Le script de sérialisation traverse ces racines et
restitue la page telle que l'utilisateur la voit.

Playwright n'est importé qu'à la première page rendue : les postes et les
tests sans navigateur ne le paient pas. Il s'installe par
`pip install playwright` puis `python -m playwright install chromium`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

log = logging.getLogger("veille")

# Ressources sans effet sur le HTML rendu : les bloquer accélère chaque page et
# épargne le site visité.
BLOCKED_RESOURCES = frozenset({"image", "media", "font"})

# Sans sélecteur d'attente, la session attend le calme du réseau, mais pas
# indéfiniment : certaines applications interrogent leur serveur en continu.
NETWORK_IDLE_CAP_MS = 10_000
# Le document est tenu pour stable quand deux lectures à cet intervalle sont
# identiques ; au-delà du plafond, il est pris tel quel (carrousels, horloges).
SETTLE_MS = 500
SETTLE_CAP_MS = 8_000

INSTALL_HINT = ("navigateur indisponible : installer Playwright "
                "(pip install playwright ; python -m playwright install chromium)")

# Sérialise le document en traversant les shadow roots ouverts.
FLATTEN_SCRIPT = """
() => {
  const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                        'link', 'meta', 'source', 'track', 'wbr']);
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const escAttr = (s) => esc(s).replace(/"/g, '&quot;');
  function ser(node) {
    if (node.nodeType === Node.TEXT_NODE) return esc(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE) return '';
    const tag = node.tagName.toLowerCase();
    let out = '<' + tag;
    for (const a of node.attributes) out += ' ' + a.name + '="' + escAttr(a.value) + '"';
    out += '>';
    if (VOID.has(tag)) return out;
    if (node.shadowRoot) for (const c of node.shadowRoot.childNodes) out += ser(c);
    for (const c of node.childNodes) out += ser(c);
    return out + '</' + tag + '>';
  }
  return '<!DOCTYPE html>' + ser(document.documentElement);
}
"""


@dataclass
class RenderedResponse:
    """Le strict nécessaire d'une réponse requests, pour une page rendue."""

    url: str
    status_code: int
    text: str
    headers: dict[str, str] = field(default_factory=lambda: {"content-type": "text/html; charset=utf-8"})

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} pour {self.url}")


def _default_playwright_factory() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dépend du poste
        raise RuntimeError(INSTALL_HINT) from exc
    return sync_playwright().start()


class BrowserSession:
    """Un navigateur Chromium sans tête, lancé à la première page demandée.

    `wait_for` est un sélecteur CSS dont l'apparition dans le document signale
    que la page a fini de s'afficher ; sans lui, la session s'en remet au calme
    du réseau. Dans les deux cas le HTML n'est lu qu'une fois le document
    stable. `for_site(site)` rend une vue de la même session réglée sur le
    sélecteur propre à une source (`render_wait_for` dans la configuration).
    """

    def __init__(self, user_agent: str = "", wait_for: str = "",
                 playwright_factory: Callable[[], Any] | None = None):
        self.user_agent = user_agent
        self.wait_for = wait_for
        self._factory = playwright_factory or _default_playwright_factory
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self.pages_rendered = 0

    def for_site(self, site: dict[str, Any]) -> "SiteBrowser":
        return SiteBrowser(self, str(site.get("render_wait_for") or ""))

    def _ensure_started(self) -> None:
        if self._context is not None:
            return
        self._playwright = self._factory()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception as exc:
            self.close()
            raise RuntimeError(f"{INSTALL_HINT} — {exc}") from exc
        self._context = self._browser.new_context(
            user_agent=self.user_agent or None, locale="fr-FR",
            viewport={"width": 1280, "height": 2000})
        self._context.route("**/*", self._filter_resources)

    @staticmethod
    def _filter_resources(route: Any, request: Any) -> None:
        if request.resource_type in BLOCKED_RESOURCES:
            route.abort()
        else:
            route.continue_()

    def get(self, url: str, timeout: float = 30, allow_redirects: bool = True,
            wait_for: str | None = None) -> RenderedResponse:
        """Rend la page et livre son HTML final, redirections suivies."""
        self._ensure_started()
        delai_ms = int(timeout * 1000)
        page = self._context.new_page()
        try:
            try:
                reponse = page.goto(url, timeout=delai_ms, wait_until="domcontentloaded")
            except Exception as exc:
                raise RuntimeError(f"rendu de {url} interrompu : {exc}") from exc
            statut = reponse.status if reponse is not None else 200
            selecteur = self.wait_for if wait_for is None else wait_for
            if selecteur:
                try:
                    page.wait_for_selector(selecteur, state="attached", timeout=delai_ms)
                except Exception:
                    log.debug("%s : sélecteur attendu « %s » absent après %s s", url, selecteur, timeout)
            else:
                try:
                    page.wait_for_load_state("networkidle", timeout=min(delai_ms, NETWORK_IDLE_CAP_MS))
                except Exception:
                    log.debug("%s : le réseau ne s'est pas calmé, document pris tel quel", url)
            html = self._settled_html(page, delai_ms)
            self.pages_rendered += 1
            return RenderedResponse(url=page.url, status_code=statut, text=html)
        finally:
            page.close()

    @staticmethod
    def _settled_html(page: Any, delai_ms: int) -> str:
        """Le document aplati, une fois que deux lectures successives coïncident."""
        precedent = None
        limite = time.monotonic() + min(delai_ms, SETTLE_CAP_MS) / 1000
        while True:
            page.wait_for_timeout(SETTLE_MS)
            html = str(page.evaluate(FLATTEN_SCRIPT))
            if html == precedent or time.monotonic() >= limite:
                return html
            precedent = html

    def close(self) -> None:
        for attribut in ("_context", "_browser"):
            objet = getattr(self, attribut)
            if objet is not None:
                try:
                    objet.close()
                except Exception:  # pragma: no cover - fermeture de secours
                    pass
                setattr(self, attribut, None)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # pragma: no cover
                pass
            self._playwright = None

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


class SiteBrowser:
    """Vue d'une `BrowserSession` réglée sur le sélecteur d'attente d'une source."""

    def __init__(self, session: BrowserSession, wait_for: str):
        self.session = session
        self.wait_for = wait_for

    def get(self, url: str, timeout: float = 30, allow_redirects: bool = True) -> RenderedResponse:
        return self.session.get(url, timeout=timeout, allow_redirects=allow_redirects, wait_for=self.wait_for)


def needs_render(site: dict[str, Any]) -> bool:
    """Dit si la source demande un rendu navigateur (`render: true`)."""
    valeur = site.get("render")
    if isinstance(valeur, str):
        return valeur.strip().lower() in ("true", "oui", "yes", "1")
    return bool(valeur)
