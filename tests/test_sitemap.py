"""Extraction depuis un plan de site, dernier recours pour un site en JavaScript."""

from __future__ import annotations

import pytest

from veille.sitemap import items_from_sitemap, parse_sitemap, title_from_slug


class TestTitleFromSlug:
    @pytest.mark.parametrize("url, attendu", [
        ("https://exemple.fr/s/topic/cybersecurite-en-etablissement", "Cybersecurite en etablissement"),
        ("https://exemple.fr/s/topic/webinaire_rh_temps_medical", "Webinaire rh temps medical"),
        ("https://exemple.fr/s/topic/un-sujet/", "Un sujet"),
    ])
    def test_rend_le_dernier_segment_lisible(self, url, attendu):
        assert title_from_slug(url) == attendu

    def test_retire_l_identifiant_technique(self):
        url = "https://exemple.fr/s/news/coactis-MCQWTTJLAJCFBKVMG6JI27VTVJWY"
        assert title_from_slug(url) == "Coactis"

    def test_decode_les_accents_percent_encodes(self):
        url = "https://exemple.fr/s/topic/journ%C3%A9e-nationale"
        assert title_from_slug(url) == "Journée nationale"

    def test_rend_une_chaine_vide_sans_segment(self):
        assert title_from_slug("https://exemple.fr/") == ""


class TestParseSitemap:
    def test_lit_les_url_et_leurs_dates(self, fixture_bytes):
        items = parse_sitemap(fixture_bytes("sitemap_news.xml"), "ANAP", 60)
        assert items[0].title == "Journée nationale de la transformation"
        assert items[0].published == "2026-08-21T14:59:48+00:00"

    def test_trie_du_plus_recent_au_plus_ancien(self, fixture_bytes):
        items = parse_sitemap(fixture_bytes("sitemap_news.xml"), "ANAP", 60)
        dates = [i.published for i in items]
        assert dates == sorted(dates, reverse=True)

    def test_ecarte_un_titre_trop_court_et_une_url_vide(self, fixture_bytes):
        items = parse_sitemap(fixture_bytes("sitemap_news.xml"), "ANAP", 60)
        assert [i.title for i in items].count("Abc") == 0
        assert all(i.link for i in items)

    def test_respecte_la_limite(self, fixture_bytes):
        assert len(parse_sitemap(fixture_bytes("sitemap_news.xml"), "ANAP", 2)) == 2

    def test_refuse_un_index_de_plans(self):
        index = b"""<?xml version="1.0"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://exemple.fr/s/sitemap-news-1.xml</loc></sitemap>
        </sitemapindex>"""
        with pytest.raises(RuntimeError, match="index"):
            parse_sitemap(index, "ANAP", 60)


class StubReponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None


class StubSession:
    def __init__(self, content: bytes):
        self.content = content
        self.urls: list[str] = []

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        return StubReponse(self.content)


class TestItemsFromSitemap:
    def test_rend_les_articles_du_plan(self, fixture_bytes):
        session = StubSession(fixture_bytes("sitemap_news.xml"))
        items = items_from_sitemap(session, "https://exemple.fr/s/sitemap.xml", "ANAP", 10, 60)
        assert len(items) == 3
        assert all(i.source == "ANAP" for i in items)

    def test_signale_un_plan_sans_url_exploitable(self):
        vide = b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'
        with pytest.raises(RuntimeError, match="aucune URL exploitable"):
            items_from_sitemap(StubSession(vide), "https://exemple.fr/s.xml", "ANAP", 10, 60)
