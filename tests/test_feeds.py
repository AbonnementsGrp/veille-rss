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
        assert [i.link for i in dedupe([self._item(l) for l in liens])] == liens

    def test_se_replie_sur_l_uid_sans_lien(self):
        items = [self._item("", "Titre A"), self._item("", "Titre B")]
        assert len(dedupe(items)) == 2
