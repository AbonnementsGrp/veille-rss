"""Extraction HTML : JSON-LD, sélecteurs CSS, notation des liens."""

from __future__ import annotations

from bs4 import BeautifulSoup

import pytest

from veille.extract import (
    date_from_text,
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


class TestDateFromText:
    """Repli quand le site ne met sa date ni dans <time> ni dans un attribut."""

    @pytest.mark.parametrize("texte, attendu", [
        ("Auteur : Tatiana CORRE Publication publiée : 25 juin 2026", "2026-06-25"),
        ("Publié le 03/02/2026 par la rédaction", "2026-02-03"),
        ("Mis à jour le 1er août 2026", "2026-08-01"),
        ("Actualité du 27 févr. 2026", "2026-02-27"),
        ("Le 15.01.2026 en bref", "2026-01-15"),
    ])
    def test_trouve_une_date_dans_une_phrase(self, texte, attendu):
        assert date_from_text(texte).startswith(attendu)

    @pytest.mark.parametrize("texte", [
        "Aucune date ici, juste 42 articles et 2026 quelque part",
        "Réf. 12345678 2026 sans date",
        "",
    ])
    def test_ne_fabrique_pas_de_date(self, texte):
        assert date_from_text(texte) == ""

    def test_les_selecteurs_se_replient_sur_le_texte_du_bloc(self):
        """Cas C2L : la date est dans le texte, hors de toute balise dédiée."""
        html = """
        <article class="post">
          <h2><a href="/a/">Plan de correction EGalim en restauration</a></h2>
          <span class="meta">Publication publiée : 25 juin 2026</span>
        </article>
        <article class="post">
          <h2><a href="/b/">CCTP restauration et fréquences de contrôle</a></h2>
          <span class="meta">Publication publiée : 10 mai 2026</span>
        </article>
        """
        items = extract_with_selectors(soup_of(html), SITE, 60)
        assert [i.published[:10] for i in items] == ["2026-06-25", "2026-05-10"]

    def test_une_balise_de_date_reste_prioritaire(self):
        html = """
        <article class="post">
          <h2><a href="/a/">Un titre suffisamment long pour passer</a></h2>
          <time datetime="2026-08-20T09:00:00+00:00">une autre mention : 25 juin 2026</time>
        </article>
        <article class="post">
          <h2><a href="/b/">Un second titre suffisamment long</a></h2>
          <time datetime="2026-08-18T09:00:00+00:00">18 août 2026</time>
        </article>
        """
        items = extract_with_selectors(soup_of(html), SITE, 60)
        assert items[0].published == "2026-08-20T09:00:00+00:00"


class TestFiltrageDeLaNavigation:
    """Rubriques, mots-clés et pagination cohabitent avec les articles."""

    def _anchor(self, html):
        return soup_of(html).find("a")

    def test_rejette_un_lien_de_rubrique(self):
        a = self._anchor('<a rel="category tag" href="/category/actualites/">La restauration collective</a>')
        assert generic_link_score(a, "exemple.fr", []) < 0

    def test_rejette_un_lien_de_pagination_par_sa_classe(self):
        a = self._anchor('<a class="next page-numbers" href="/suite/">Aller à la page suivante</a>')
        assert generic_link_score(a, "exemple.fr", []) < 0

    def test_rejette_un_lien_de_pagination_par_son_url(self):
        for href in ("/category/actus/page/2/", "/actualites?paged=3"):
            a = self._anchor(f'<a href="{href}">Aller à la page suivante</a>')
            assert generic_link_score(a, "exemple.fr", []) < 0

    def test_rejette_les_pages_de_mots_cles_et_d_auteurs(self):
        for href in ("/tag/egalim/", "/author/tatiana-corre/", "/etiquette/cantine/"):
            a = self._anchor(f'<a href="{href}">Un libellé suffisamment long</a>')
            assert generic_link_score(a, "exemple.fr", []) < 0

    def test_conserve_le_lien_permanent_d_un_article(self):
        """rel="bookmark" est le permalien WordPress : il ne doit pas tomber."""
        a = self._anchor('<a rel="bookmark" href="/plan-correction-egalim/">Plan de correction EGalim</a>')
        assert generic_link_score(a, "exemple.fr", []) > 0


class StubReponsePage:
    def __init__(self, html: str, url: str = "https://exemple.fr/actualites/"):
        self.text = html
        self.url = url
        self.ok = True
        self.headers = {"content-type": "text/html"}

    def raise_for_status(self) -> None:
        return None


class StubSessionPage:
    def __init__(self, html: str):
        self.html = html

    def get(self, url, timeout=None, allow_redirects=False):
        return StubReponsePage(self.html, url)


class TestCascadeDesStrategies:
    """Les liens génériques ne doivent pas polluer un résultat déjà propre."""

    PAGE_MIXTE = """
    <main>
      <article class="post">
        <h2><a href="/actualites/premier-sujet/">Premier sujet de la liste</a></h2>
      </article>
      <article class="post">
        <h2><a href="/actualites/deuxieme-sujet/">Deuxième sujet de la liste</a></h2>
      </article>
    </main>
    <aside>
      <a href="/faq/">Découvrez la réponse dans notre FAQ</a>
      <a href="/agenda/assemblee-generale/">Assemblée générale ordinaire du syndicat</a>
    </aside>
    """

    def test_les_selecteurs_gagnants_excluent_le_bruit_lateral(self):
        from veille.extract import scrape_page
        items, method = scrape_page(StubSessionPage(self.PAGE_MIXTE), dict(SITE), 10, 60)
        assert method == "html_selectors"
        assert [i.title for i in items] == ["Premier sujet de la liste", "Deuxième sujet de la liste"]

    def test_les_liens_generiques_prennent_le_relais_si_rien_d_autre(self):
        from veille.extract import scrape_page
        page = """
        <main>
          <p><a href="/actualites/un-sujet-de-fond/">Un sujet de fond traité en détail</a></p>
          <p><a href="/actualites/un-autre-sujet/">Un autre sujet également détaillé</a></p>
        </main>
        """
        items, method = scrape_page(StubSessionPage(page), dict(SITE), 10, 60)
        assert method == "generic_links"
        assert len(items) == 2

    def test_le_json_ld_est_prioritaire_dans_le_libelle(self, fixture_text):
        from veille.extract import scrape_page
        _, method = scrape_page(StubSessionPage(fixture_text("page_json_ld.html")), dict(SITE), 10, 60)
        assert method == "json_ld+html"
