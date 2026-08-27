"""Lecture des flux et déduplication."""

from __future__ import annotations

import pytest

from veille.feeds import parse_feed_bytes
from veille.models import Item, dedupe


class TestParseFeedBytes:
    def test_lit_les_articles_d_un_flux_wordpress(self, fixture_bytes):
        items = parse_feed_bytes(fixture_bytes("wordpress_feed.xml"), "Ma source", 60)
        assert [i.title for i in items] == [
            "Deuxième article, publié le 10 juillet",
            "Premier article, publié le 25 août",
        ]
        assert all(i.source == "Ma source" for i in items)

    def test_normalise_les_dates_en_iso_utc(self, fixture_bytes):
        items = parse_feed_bytes(fixture_bytes("wordpress_feed.xml"), "S", 60)
        assert items[0].published == "2026-07-10T08:42:08+00:00"
        assert items[1].published == "2026-08-25T08:02:53+00:00"

    def test_ecarte_un_article_sans_lien(self, fixture_bytes):
        items = parse_feed_bytes(fixture_bytes("wordpress_feed.xml"), "S", 60)
        assert "Article sans lien exploitable" not in [i.title for i in items]

    def test_ecarte_les_doublons_de_lien(self, fixture_bytes):
        items = parse_feed_bytes(fixture_bytes("wordpress_feed.xml"), "S", 60)
        assert len({i.link for i in items}) == len(items)

    def test_respecte_la_limite_d_articles(self, fixture_bytes):
        assert len(parse_feed_bytes(fixture_bytes("wordpress_feed.xml"), "S", 1)) == 1

    def test_refuse_une_page_html_servie_comme_flux(self, fixture_text):
        """Cas C2L : /feed/ renvoie la page HTML de la catégorie, pas un flux."""
        with pytest.raises(RuntimeError, match="Flux RSS invalide"):
            parse_feed_bytes(fixture_text("page_selectors.html").encode("utf-8"), "S", 60)

    def test_refuse_un_contenu_vide(self):
        with pytest.raises(RuntimeError, match="Flux RSS invalide"):
            parse_feed_bytes(b"ceci n'est pas un flux", "S", 60)


class TestDedupe:
    def _item(self, link, titre="T"):
        return Item(source="S", title=titre, link=link)

    def test_conserve_la_premiere_occurrence(self):
        items = [self._item("https://exemple.fr/a", "gardé"), self._item("https://exemple.fr/a", "écarté")]
        assert [i.title for i in dedupe(items)] == ["gardé"]

    def test_ignore_la_barre_finale_et_la_casse(self):
        items = [self._item("https://exemple.fr/A/"), self._item("https://exemple.fr/a")]
        assert len(dedupe(items)) == 1

    def test_preserve_l_ordre(self):
        liens = [f"https://exemple.fr/{n}" for n in range(5)]
        items = [self._item(lien, f"Titre {n}") for n, lien in enumerate(liens)]
        assert [i.link for i in dedupe(items)] == liens

    def test_se_replie_sur_l_uid_sans_lien(self):
        items = [self._item("", "Titre A"), self._item("", "Titre B")]
        assert len(dedupe(items)) == 2


class TestCleanLink:
    def test_retire_les_parametres_de_campagne(self):
        from veille.urls import clean_link
        sale = ("https://www.banquedesterritoires.fr/un-article"
                "?pk_campaign=Flux%20RSS&pk_kwd=publics-fragiles&pk_source=Localtis&pk_medium=RSS")
        assert clean_link(sale) == "https://www.banquedesterritoires.fr/un-article"

    def test_retire_utm_et_identifiants_de_clic(self):
        from veille.urls import clean_link
        assert clean_link("https://exemple.fr/a?utm_source=x&fbclid=y") == "https://exemple.fr/a"

    def test_conserve_les_parametres_utiles(self):
        from veille.urls import clean_link
        assert clean_link("https://exemple.fr/a?id=42&utm_source=x") == "https://exemple.fr/a?id=42"

    def test_laisse_une_url_sans_parametre_intacte(self):
        from veille.urls import clean_link
        assert clean_link("https://exemple.fr/a/") == "https://exemple.fr/a/"

    def test_un_item_normalise_son_lien(self):
        a = Item("S", "T", "https://exemple.fr/a?pk_kwd=jeunesse")
        b = Item("S", "T", "https://exemple.fr/a")
        assert a.link == b.link == "https://exemple.fr/a"
        assert a.uid == b.uid

    def test_deux_rubriques_ne_produisent_plus_de_doublon(self):
        """Cas Localtis : un même article servi par deux flux thématiques."""
        items = [
            Item("S", "Même article", "https://exemple.fr/a?pk_kwd=jeunesse"),
            Item("S", "Même article", "https://exemple.fr/a?pk_kwd=publics-fragiles"),
        ]
        assert len(dedupe(items)) == 1


class TestDedupeParTitre:
    """Un même article peut être servi sous deux URL par un même site."""

    def _item(self, link, titre, source="S"):
        return Item(source=source, title=titre, link=link)

    def test_ecarte_le_meme_titre_dans_une_source(self):
        """Cas Igas : Drupal publie un rapport comme actualité et comme page."""
        items = [
            self._item("https://igas.gouv.fr/le-rapport", "Le temps de travail des médecins"),
            self._item("https://igas.gouv.fr/le-rapport-0", "Le temps de travail des médecins"),
        ]
        garde = dedupe(items)
        assert len(garde) == 1
        assert garde[0].link == "https://igas.gouv.fr/le-rapport"

    def test_ignore_la_casse_et_les_espaces_du_titre(self):
        items = [
            self._item("https://exemple.fr/a", "Le  Temps de   travail"),
            self._item("https://exemple.fr/b", "le temps de travail"),
        ]
        assert len(dedupe(items)) == 1

    def test_deux_sources_gardent_chacune_leur_article(self):
        """Deux sources qui couvrent le même sujet restent toutes deux lisibles."""
        items = [
            self._item("https://a.fr/x", "Réforme des retraites", source="Source A"),
            self._item("https://b.fr/y", "Réforme des retraites", source="Source B"),
        ]
        assert len(dedupe(items)) == 2

    def test_un_titre_vide_ne_regroupe_rien(self):
        items = [self._item("https://exemple.fr/a", ""), self._item("https://exemple.fr/b", "")]
        assert len(dedupe(items)) == 2

    def test_le_controleur_frontal_ne_dedouble_plus_les_articles(self):
        """Cas CNSA : le flux sert /actualites/x et /index%2Ephp/actualites/x."""
        items = [
            self._item("https://www.cnsa.fr/actualites/canicule", "Canicule : la CNSA s'associe"),
            self._item("https://www.cnsa.fr/index%2Ephp/actualites/canicule", "Canicule : la CNSA s'associe"),
        ]
        garde = dedupe(items)
        assert len(garde) == 1
        assert "index" not in garde[0].link
