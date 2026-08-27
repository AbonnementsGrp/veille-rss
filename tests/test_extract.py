"""Extraction HTML : JSON-LD, sélecteurs CSS, notation des liens."""

from __future__ import annotations

from bs4 import BeautifulSoup

from veille.extract import (
    extract_generic_links,
    extract_with_selectors,
    generic_link_score,
    parse_json_ld,
)
from veille.text import clean_text

SITE = {"name": "Ma source", "url": "https://exemple.fr/actualites/"}


def soup_of(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, "html.parser")


class TestParseJsonLd:
    def test_extrait_les_articles_du_graphe(self, fixture_text):
        items = parse_json_ld(soup_of(fixture_text("page_json_ld.html")), "S", SITE["url"], 60)
        assert {i.title for i in items} == {
            "Réforme du financement des crèches",
            "Bilan de la saison touristique",
        }

    def test_ignore_les_types_qui_ne_sont_pas_des_articles(self, fixture_text):
        items = parse_json_ld(soup_of(fixture_text("page_json_ld.html")), "S", SITE["url"], 60)
        assert "Ne doit pas être extrait" not in [i.title for i in items]

    def test_rend_les_liens_absolus(self, fixture_text):
        items = parse_json_ld(soup_of(fixture_text("page_json_ld.html")), "S", SITE["url"], 60)
        assert all(i.link.startswith("https://exemple.fr/") for i in items)

    def test_normalise_les_dates(self, fixture_text):
        items = parse_json_ld(soup_of(fixture_text("page_json_ld.html")), "S", SITE["url"], 60)
        dates = {i.title: i.published for i in items}
        # 09:30 en +02:00 devient 07:30 UTC, et le 10 juillet reste le 10 juillet.
        assert dates["Réforme du financement des crèches"] == "2026-07-10T07:30:00+00:00"

    def test_ne_renvoie_rien_sans_json_ld(self, fixture_text):
        assert parse_json_ld(soup_of(fixture_text("page_selectors.html")), "S", SITE["url"], 60) == []


class TestExtractWithSelectors:
    def test_extrait_titre_lien_resume_et_date(self, fixture_text):
        items = extract_with_selectors(soup_of(fixture_text("page_selectors.html")), SITE, 60)
        premier = items[0]
        assert premier.title == "Premier sujet de la liste"
        assert premier.link == "https://exemple.fr/actualites/premier-sujet/"
        assert premier.description == "Résumé du premier sujet."
        assert premier.published == "2026-08-20T09:00:00+00:00"

    def test_ecarte_un_bloc_sans_lien_et_un_titre_trop_court(self, fixture_text):
        items = extract_with_selectors(soup_of(fixture_text("page_selectors.html")), SITE, 60)
        titres = [i.title for i in items]
        assert titres == ["Premier sujet de la liste", "Deuxième sujet de la liste"]

    def test_respecte_la_limite(self, fixture_text):
        assert len(extract_with_selectors(soup_of(fixture_text("page_selectors.html")), SITE, 1)) == 1

    def test_utilise_les_selecteurs_configures(self):
        html = """
        <div class="ligne"><span class="titre"><a href="/a/">Un titre suffisamment long</a></span></div>
        <div class="ligne"><span class="titre"><a href="/b/">Un autre titre assez long</a></span></div>
        """
        site = {**SITE, "selectors": {"item": [".ligne"], "title": [".titre a"]}}
        items = extract_with_selectors(soup_of(html), site, 60)
        assert len(items) == 2

    def test_exige_au_moins_deux_blocs_pour_retenir_un_selecteur(self):
        html = '<article class="post"><h2><a href="/a/">Un seul bloc, ignoré</a></h2></article>'
        assert extract_with_selectors(soup_of(html), SITE, 60) == []


class TestGenericLinkScore:
    def _anchor(self, html):
        return soup_of(html).find("a")

    def test_rejette_un_lien_externe(self):
        a = self._anchor('<a href="https://autre-site.fr/actualites/x">Un titre suffisamment long</a>')
        assert generic_link_score(a, "exemple.fr", []) < 0

    def test_rejette_un_texte_trop_court(self):
        a = self._anchor('<a href="/actualites/x">Lire</a>')
        assert generic_link_score(a, "exemple.fr", []) < 0

    def test_rejette_la_navigation_et_les_reseaux_sociaux(self):
        for html in (
            '<a href="/mentions-legales/">Mentions légales du site</a>',
            '<a href="/page">Retrouvez-nous sur Facebook</a>',
            '<a href="mailto:contact@exemple.fr">Nous écrire par courriel</a>',
        ):
            assert generic_link_score(self._anchor(html), "exemple.fr", []) < 0

    def test_favorise_un_lien_d_article(self):
        article = self._anchor('<a href="/actualites/2026/un-sujet">Un titre d\'article assez long</a>')
        quelconque = self._anchor('<a href="/pages/informations-diverses">Un titre quelconque de la page</a>')
        assert generic_link_score(article, "exemple.fr", []) > generic_link_score(quelconque, "exemple.fr", [])

    def test_bonifie_les_motifs_configures(self):
        a = self._anchor('<a href="/s/article/xyz">Un titre suffisamment long ici</a>')
        assert generic_link_score(a, "exemple.fr", ["/s/article/"]) > generic_link_score(a, "exemple.fr", [])


class TestExtractGenericLinks:
    def test_ne_retient_que_les_liens_d_articles(self, fixture_text):
        items = extract_generic_links(soup_of(fixture_text("page_selectors.html")), SITE, 60)
        liens = [i.link for i in items]
        assert "https://exemple.fr/actualites/premier-sujet/" in liens
        assert not any("mentions-legales" in l for l in liens)
        assert not any("facebook" in l for l in liens)


class TestCleanText:
    def test_retire_le_balisage(self):
        assert clean_text("<p>Bonjour <strong>le monde</strong></p>") == "Bonjour le monde"

    def test_compacte_les_espaces(self):
        assert clean_text("trop   d'espaces\n\tet de tabulations") == "trop d'espaces et de tabulations"

    def test_tronque_a_la_limite(self):
        assert len(clean_text("a" * 5000, limit=100)) == 100

    def test_tolere_none(self):
        assert clean_text(None) == ""
