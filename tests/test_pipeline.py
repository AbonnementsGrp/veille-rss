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


class TestModePage:
    """`mode: page` interdit la découverte de flux."""

    def test_ignore_la_decouverte(self):
        site = {"name": "SNRC", "url": "https://exemple.fr/actu/", "mode": "page"}
        assert resolve_feed_url(ExplodingSession(), site, 10) == ""

    def test_le_flux_officiel_reste_prioritaire_sur_le_mode(self):
        site = {"name": "S", "url": "https://exemple.fr/actu/", "mode": "page",
                "official_feed": "https://exemple.fr/rss.xml"}
        assert resolve_feed_url(ExplodingSession(), site, 10) == "https://exemple.fr/rss.xml"


class TestModeSitemap:
    """`mode: sitemap` remplace toute autre stratégie."""

    def _site(self):
        return {
            "name": "ANAP - Actualités",
            "url": "https://exemple.fr/s/actualites",
            "mode": "sitemap",
            "sitemap": "https://exemple.fr/s/sitemap-news-1.xml",
        }

    def test_lit_le_plan_de_site(self, fixture_bytes):
        session = StubSession(fixture_bytes("sitemap_news.xml"))
        items, method = fetch_items(session, self._site(), "", 10, 60)
        assert method == "plan de site"
        assert len(items) == 3
        assert session.urls == ["https://exemple.fr/s/sitemap-news-1.xml"]

    def test_n_essaie_ni_flux_ni_page(self):
        assert resolve_feed_url(ExplodingSession(), self._site(), 10) == ""

    def test_exige_la_cle_sitemap(self):
        site = {k: v for k, v in self._site().items() if k != "sitemap"}
        with pytest.raises(RuntimeError, match="sans clé 'sitemap'"):
            fetch_items(ExplodingSession(), site, "", 10, 60)


RESUME = ("Le Premier ministre a confié à l'Inspection générale des affaires sociales "
          "une mission sur le temps de travail des médecins.")


class SessionPageArticle:
    """Sert une page d'article porteuse d'un résumé, et compte les visites."""

    def __init__(self):
        self.urls: list[str] = []

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        return StubResponse(
            f'<html><head><meta property="og:description" content="{RESUME}">'
            "</head><body></body></html>".encode("utf-8"), url)


class TestReuseKnownDescriptions:
    def test_reprend_un_resume_deja_connu(self):
        from veille.pipeline import reuse_known_descriptions
        item = Item("S", "T", "https://exemple.fr/a")
        history = {item.uid: {"description": RESUME}}
        reuse_known_descriptions([item], history)
        assert item.description == RESUME

    def test_ne_remplace_pas_un_resume_fourni_par_le_flux(self):
        from veille.pipeline import reuse_known_descriptions
        item = Item("S", "T", "https://exemple.fr/a", description="Résumé du flux")
        reuse_known_descriptions([item], {item.uid: {"description": RESUME}})
        assert item.description == "Résumé du flux"


class TestEnrichDescriptions:
    def _item(self):
        return Item("S", "Un titre", "https://exemple.fr/a")

    def test_lit_la_page_et_garde_le_resume(self):
        from veille.pipeline import enrich_descriptions
        item = self._item()
        history = {item.uid: {"uid": item.uid}}
        session = SessionPageArticle()
        assert enrich_descriptions(session, [item], history, 5, 10) == 1
        assert item.description == RESUME
        assert history[item.uid]["description"] == RESUME

    def test_ne_visite_qu_une_fois_le_meme_article(self):
        from veille.pipeline import enrich_descriptions
        item = self._item()
        history = {item.uid: {"uid": item.uid, "description_checked": True}}
        session = SessionPageArticle()
        assert enrich_descriptions(session, [item], history, 5, 10) == 0
        assert session.urls == []

    def test_respecte_le_budget(self):
        from veille.pipeline import enrich_descriptions
        items = [Item("S", f"Titre {n}", f"https://exemple.fr/{n}") for n in range(5)]
        history = {i.uid: {"uid": i.uid} for i in items}
        session = SessionPageArticle()
        assert enrich_descriptions(session, items, history, 2, 10) == 2
        assert len(session.urls) == 2

    def test_une_page_injoignable_ne_fait_pas_echouer_la_source(self):
        from veille.pipeline import enrich_descriptions
        item = self._item()
        history = {item.uid: {"uid": item.uid}}
        assert enrich_descriptions(ExplodingSession(), [item], history, 5, 10) == 1
        assert item.description == ""
        assert history[item.uid]["description_checked"] is True

    def test_ignore_un_article_absent_de_l_historique(self):
        from veille.pipeline import enrich_descriptions
        session = SessionPageArticle()
        assert enrich_descriptions(session, [self._item()], {}, 5, 10) == 0


class TestRecordInHistoryEtResumes:
    def test_un_resume_obtenu_survit_a_un_flux_qui_n_en_donne_pas(self):
        history: dict = {}
        item = Item("S", "Un titre", "https://exemple.fr/a", description="")
        record_in_history([item], history)
        history[item.uid]["description"] = RESUME
        record_in_history([Item("S", "Un titre", "https://exemple.fr/a")], history)
        assert history[item.uid]["description"] == RESUME


class TestFluxFiltreParCategorie:
    """Un flux filtré peut ne rien avoir de neuf : ce n'est pas un échec."""

    def _site(self, categories):
        return {"name": "C2L", "url": "https://exemple.fr/category/actus/",
                "official_feed": "https://exemple.fr/feed/?post_type=post", "feed_categories": categories}

    def test_transmet_le_filtre_au_flux(self):
        from tests.test_feeds import FLUX_CATEGORISE
        session = StubSession(FLUX_CATEGORISE)
        items, method = fetch_items(session, self._site(["La restauration collective"]), "https://exemple.fr/feed/?post_type=post", 10, 60)
        assert method == "flux officiel"
        assert [i.link for i in items] == ["https://exemple.fr/b", "https://exemple.fr/c"]

    def test_un_filtre_sans_resultat_ne_declenche_pas_de_repli(self):
        from tests.test_feeds import FLUX_CATEGORISE
        session = StubSession(FLUX_CATEGORISE)
        items, method = fetch_items(session, self._site(["Inexistante"]), "https://exemple.fr/feed/?post_type=post", 10, 60)
        assert items == [] and method == "flux officiel"
        assert session.urls == ["https://exemple.fr/feed/?post_type=post"], "la page ne doit pas être visitée"

    def test_l_identite_transporte_le_filtre_vers_status_json(self):
        from veille.pipeline import identity
        assert identity(self._site(["La restauration collective"]))["feed_categories"] == ["La restauration collective"]
        assert identity({"name": "S", "url": "https://s.fr/"})["feed_categories"] == []


class NavigateurFactice:
    """Tient lieu de BrowserSession : sert une page rendue, note adresses et sélecteurs."""

    def __init__(self, html: str):
        self.html = html
        self.urls: list[str] = []
        self.selecteurs: list[str] = []

    def for_site(self, site):
        self.selecteurs.append(str(site.get("render_wait_for") or ""))
        return self

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        return StubResponse(self.html.encode("utf-8"), url)


class TestRenduNavigateur:
    """`render: true` : la page est lue par le navigateur, l'extraction reste la même."""

    def _site(self, **extra):
        return {"name": "Site JS", "url": "https://exemple.fr/actualites/", "mode": "page", "render": True, **extra}

    def test_la_page_est_lue_par_le_navigateur_et_la_methode_le_dit(self, fixture_text):
        navigateur = NavigateurFactice(fixture_text("page_selectors.html"))
        items, method = fetch_items(ExplodingSession(), self._site(render_wait_for="article"), "", 10, 60, navigateur)
        assert method.startswith("navigateur : ")
        assert items
        assert navigateur.urls == ["https://exemple.fr/actualites/"]
        assert navigateur.selecteurs == ["article"], "le sélecteur d'attente de la source est transmis"

    def test_sans_navigateur_la_source_est_en_erreur_explicite(self):
        with pytest.raises(RuntimeError, match="navigateur"):
            fetch_items(StubSession(b"<html></html>"), self._site(), "", 10, 60)

    def test_aucune_decouverte_de_flux_sur_un_site_rendu(self):
        assert resolve_feed_url(ExplodingSession(), self._site(), 10) == ""

    def test_en_mode_plan_de_site_le_plan_reste_lu_en_http(self, fixture_bytes):
        session = StubSession(fixture_bytes("sitemap_news.xml"))
        navigateur = NavigateurFactice("<html></html>")
        site = {"name": "ANAP", "url": "https://exemple.fr/s/actualites", "mode": "sitemap",
                "sitemap": "https://exemple.fr/s/sitemap-news-1.xml", "render": True}
        items, method = fetch_items(session, site, "", 10, 60, navigateur)
        assert method == "plan de site"
        assert len(items) == 3
        assert navigateur.urls == [], "le navigateur ne sert qu'aux pages d'articles"

    def test_l_identite_signale_le_rendu(self):
        from veille.pipeline import identity
        assert identity(self._site())["render"] is True
        assert identity({"name": "S", "url": "https://s.fr/"})["render"] is False


TITRE_REEL = "Handicap : l'Anap outille la transformation vers une offre de services coordonnés"


class SessionPageArticleTitree(SessionPageArticle):
    """Page d'article dont les métadonnées de partage portent aussi le titre."""

    def __init__(self, titre: str = TITRE_REEL):
        super().__init__()
        self.titre = titre

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        return StubResponse(
            f'<html><head><title>Site de l\'Anap</title><meta property="og:title" content="{self.titre}">'
            f'<meta property="og:description" content="{RESUME}"></head><body></body></html>'.encode("utf-8"), url)


class TestEnrichissementDesTitres:
    """Les titres tirés d'un plan de site ne sont que des ébauches : la page fait foi."""

    def _ebauche(self):
        return Item("ANAP", "Handicap offre services coordonnes transformation",
                    "https://exemple.fr/s/article/handicap-offre-services-coordonnes-transformation")

    def test_le_titre_de_la_page_remplace_l_ebauche_sans_changer_l_identite(self):
        from veille.pipeline import enrich_descriptions
        item = self._ebauche()
        identite = item.uid
        history = {item.uid: {"uid": item.uid, "title": item.title}}
        assert enrich_descriptions(SessionPageArticleTitree(), [item], history, 5, 10, titles=True) == 1
        assert item.title == TITRE_REEL
        assert item.description == RESUME
        assert item.uid == identite
        assert history[identite]["title"] == TITRE_REEL
        assert history[identite]["title_enriched"] is True

    def test_le_titre_corrige_survit_a_l_execution_suivante(self):
        from veille.pipeline import enrich_descriptions
        item = self._ebauche()
        history: dict = {}
        record_in_history([item], history)
        enrich_descriptions(SessionPageArticleTitree(), [item], history, 5, 10, titles=True)

        revenu = self._ebauche()  # le plan de site redonne l'ébauche à chaque exécution
        assert record_in_history([revenu], history) == 0
        assert revenu.title == TITRE_REEL
        assert history[revenu.uid]["title"] == TITRE_REEL

    def test_sans_titles_le_titre_d_origine_est_conserve(self):
        from veille.pipeline import enrich_descriptions
        item = Item("S", "Titre du flux", "https://exemple.fr/a")
        history = {item.uid: {"uid": item.uid}}
        enrich_descriptions(SessionPageArticleTitree(), [item], history, 5, 10)
        assert item.title == "Titre du flux"
        assert item.description == RESUME
        assert "title_enriched" not in history[item.uid]

    @pytest.mark.parametrize("titre", ["ANAP", "SIGLE EN CAPITALES", "Court"])
    def test_un_titre_douteux_est_ignore(self, titre):
        from veille.pipeline import enrich_descriptions
        item = self._ebauche()
        history = {item.uid: {"uid": item.uid}}
        enrich_descriptions(SessionPageArticleTitree(titre), [item], history, 5, 10, titles=True)
        assert item.title == "Handicap offre services coordonnes transformation"
        assert item.description == RESUME, "le résumé, lui, est pris"

    def test_un_article_deja_resume_mais_au_titre_ebauche_est_visite(self):
        from veille.pipeline import enrich_descriptions
        item = self._ebauche()
        item.description = "Résumé déjà connu."
        history = {item.uid: {"uid": item.uid, "description": item.description}}
        session = SessionPageArticleTitree()
        assert enrich_descriptions(session, [item], history, 5, 10, titles=True) == 1
        assert item.title == TITRE_REEL
        assert item.description == "Résumé déjà connu.", "un résumé connu n'est pas remplacé"

    def test_une_page_visitee_sans_navigateur_est_revisitee_pour_son_titre(self):
        """Avant le navigateur, les pages ANAP ont été visitées en vain : la marque ne doit pas bloquer le titre."""
        from veille.pipeline import enrich_descriptions
        item = self._ebauche()
        history = {item.uid: {"uid": item.uid, "description_checked": True}}
        session = SessionPageArticleTitree()
        assert enrich_descriptions(session, [item], history, 5, 10, titles=True) == 1
        assert item.title == TITRE_REEL
        assert item.description == RESUME, "le résumé profite de la seconde visite"
        assert history[item.uid]["title_checked"] is True

    def test_un_titre_introuvable_n_est_cherche_qu_une_fois(self):
        from veille.pipeline import enrich_descriptions
        item = self._ebauche()
        history = {item.uid: {"uid": item.uid}}
        session = SessionPageArticle()  # page sans og:title
        assert enrich_descriptions(session, [item], history, 5, 10, titles=True) == 1
        assert item.title == "Handicap offre services coordonnes transformation"
        assert enrich_descriptions(session, [item], history, 5, 10, titles=True) == 0
        assert len(session.urls) == 1

    def test_sans_titles_la_marque_du_titre_n_est_pas_posee(self):
        from veille.pipeline import enrich_descriptions
        item = Item("S", "Titre du flux", "https://exemple.fr/a")
        history = {item.uid: {"uid": item.uid}}
        enrich_descriptions(SessionPageArticleTitree(), [item], history, 5, 10)
        assert "title_checked" not in history[item.uid]

    def test_un_article_deja_resume_au_titre_sur_n_est_pas_visite(self):
        from veille.pipeline import enrich_descriptions
        item = Item("S", "Titre du flux", "https://exemple.fr/a", description="Résumé du flux")
        history = {item.uid: {"uid": item.uid}}
        session = SessionPageArticleTitree()
        assert enrich_descriptions(session, [item], history, 5, 10) == 0
        assert session.urls == []
