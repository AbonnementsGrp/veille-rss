"""Orchestration : nommage des sorties, résolution du flux, historique.

Ces tests n'accèdent pas au réseau : la session HTTP est remplacée par un
objet factice qui rend un contenu connu.
"""

from __future__ import annotations

import pytest

from veille.models import Item
from veille.pipeline import (
    fetch_items,
    output_name_for,
    read_feed,
    record_in_history,
    resolve_feed_url,
)


class StubResponse:
    def __init__(self, content: bytes, url: str = "https://exemple.fr/feed/"):
        self.content = content
        self.text = content.decode("utf-8", "replace")
        self.url = url
        self.ok = True
        self.headers = {"content-type": "application/xml"}

    def raise_for_status(self) -> None:
        return None


class StubSession:
    """Session HTTP factice : sert un contenu fixe et note les URL demandées."""

    def __init__(self, content: bytes = b""):
        self.content = content
        self.urls: list[str] = []

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        return StubResponse(self.content, url)


class ExplodingSession:
    """Session qui échoue si on l'utilise : prouve l'absence d'appel réseau."""

    def get(self, *a, **kw):
        raise AssertionError("aucune requête réseau ne devait être émise")


class TestOutputNameFor:
    def test_utilise_le_nom_configure(self):
        assert output_name_for({"name": "CNSA", "output": "cnsa.xml"}) == "cnsa.xml"

    def test_deduit_un_nom_du_libelle_de_la_source(self):
        assert output_name_for({"name": "Localtis — Publics fragiles"}) == "localtis-publics-fragiles.xml"

    def test_ne_laisse_pas_de_tiret_aux_extremites(self):
        assert output_name_for({"name": "  ANAP !  "}) == "anap.xml"


class TestResolveFeedUrl:
    def test_le_flux_configure_court_circuite_la_decouverte(self):
        site = {"name": "S", "url": "https://exemple.fr/actu/", "official_feed": "https://exemple.fr/rss.xml"}
        assert resolve_feed_url(ExplodingSession(), site, 10) == "https://exemple.fr/rss.xml"

    def test_rend_une_chaine_vide_si_rien_n_est_trouve(self, fixture_text):
        session = StubSession(fixture_text("page_selectors.html").encode("utf-8"))
        assert resolve_feed_url(session, {"name": "S", "url": "https://exemple.fr/actu/"}, 10) == ""


class TestFetchItems:
    def test_lit_un_flux_officiel(self, fixture_bytes):
        session = StubSession(fixture_bytes("wordpress_feed.xml"))
        site = {"name": "S", "url": "https://exemple.fr/actu/", "official_feed": "https://exemple.fr/rss.xml"}
        items, method = fetch_items(session, site, site["official_feed"], 10, 60)
        assert method == "flux officiel"
        assert len(items) == 2

    def test_distingue_un_flux_decouvert_d_un_flux_configure(self, fixture_bytes):
        session = StubSession(fixture_bytes("wordpress_feed.xml"))
        site = {"name": "S", "url": "https://exemple.fr/actu/"}
        _, method = fetch_items(session, site, "https://exemple.fr/feed/", 10, 60)
        assert method == "flux détecté"

    def test_signale_une_source_sans_aucun_article(self):
        """Cas ANAP : la page est servie, mais aucune stratégie n'y trouve d'article."""
        session = StubSession(b"<html><body><p>Rien a extraire ici</p></body></html>")
        site = {"name": "S", "url": "https://exemple.fr/vide/"}
        with pytest.raises(RuntimeError, match="Aucun article"):
            fetch_items(session, site, "", 10, 60)


class TestRecordInHistory:
    def _item(self, link="https://exemple.fr/a"):
        return Item(source="S", title="Un article", link=link, published="2026-08-25T10:00:00+00:00")

    def test_compte_les_nouveautes(self):
        history: dict = {}
        assert record_in_history([self._item("https://exemple.fr/a"), self._item("https://exemple.fr/b")], history) == 2
        assert len(history) == 2

    def test_ne_recompte_pas_un_article_deja_vu(self):
        history: dict = {}
        record_in_history([self._item()], history)
        assert record_in_history([self._item()], history) == 0

    def test_conserve_la_date_de_premiere_vue(self):
        history: dict = {}
        record_in_history([self._item()], history)
        premiere_vue = next(iter(history.values()))["first_seen"]
        item = self._item()
        record_in_history([item], history)
        assert item.first_seen == premiere_vue
        assert next(iter(history.values()))["first_seen"] == premiere_vue

    def test_renseigne_l_uid_dans_l_enregistrement(self):
        history: dict = {}
        item = self._item()
        record_in_history([item], history)
        assert history[item.uid]["uid"] == item.uid


class FailingFeedSession:
    """Sert une page HTML sur l'URL du flux, la vraie page sur l'URL du site.

    Reproduit le cas C2L : le `/feed/` annoncé renvoie la page de la rubrique.
    """

    def __init__(self, page: bytes, feed_url: str):
        self.page = page
        self.feed_url = feed_url
        self.urls: list[str] = []

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        reponse = StubResponse(self.page, url)
        reponse.headers = {"content-type": "text/html; charset=UTF-8"}
        return reponse


class TestRepliSurLaPage:
    def _site(self):
        return {
            "name": "C2L Solutions",
            "url": "https://exemple.fr/category/actus/",
            "official_feed": "https://exemple.fr/category/actus/feed/",
        }

    def test_un_flux_officiel_qui_sert_du_html_ne_condamne_plus_la_source(self, fixture_text):
        site = self._site()
        session = FailingFeedSession(fixture_text("page_selectors.html").encode("utf-8"), site["official_feed"])
        items, method = fetch_items(session, site, site["official_feed"], 10, 60)
        assert len(items) == 2
        assert method.startswith("repli :")

    def test_le_repli_se_fait_sur_la_page_configuree(self, fixture_text):
        site = self._site()
        session = FailingFeedSession(fixture_text("page_selectors.html").encode("utf-8"), site["official_feed"])
        fetch_items(session, site, site["official_feed"], 10, 60)
        assert site["url"] in session.urls

    def test_l_erreur_cumule_les_deux_echecs(self):
        site = self._site()
        session = FailingFeedSession(b"<html><body><p>Rien du tout ici</p></body></html>", site["official_feed"])
        with pytest.raises(RuntimeError) as excinfo:
            fetch_items(session, site, site["official_feed"], 10, 60)
        message = str(excinfo.value)
        assert "ne sert pas un flux" in message
        assert "aucun article" in message

    def test_un_flux_valide_n_entraine_aucun_repli(self, fixture_bytes):
        site = self._site()
        session = StubSession(fixture_bytes("wordpress_feed.xml"))
        items, method = fetch_items(session, site, site["official_feed"], 10, 60)
        assert method == "flux officiel"
        assert session.urls == [site["official_feed"]]


class TestReadFeed:
    def test_refuse_une_page_html(self, fixture_text):
        session = FailingFeedSession(fixture_text("page_selectors.html").encode("utf-8"), "https://exemple.fr/feed/")
        with pytest.raises(RuntimeError, match="ne sert pas un flux"):
            read_feed(session, "https://exemple.fr/feed/", "S", 10, 60)

    def test_accepte_un_flux(self, fixture_bytes):
        session = StubSession(fixture_bytes("wordpress_feed.xml"))
        assert len(read_feed(session, "https://exemple.fr/feed/", "S", 10, 60)) == 2
