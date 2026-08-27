"""Résumé lu sur la page d'un article, quand le flux n'en fournit pas."""

from __future__ import annotations

import pytest

from veille.enrich import describe_article, looks_like_summary

RESUME_REEL = ("Le Premier ministre a confié à l'Inspection générale des affaires sociales "
               "une mission sur le temps de travail des médecins.")
LISTE_DE_NOMS = ("François Auvigne, Rémy Slove, Léonore Lafargue, Olivier Pernet-Coudrier, "
                 "Noémie Carlier (IGF), Thomas Le Ludec, Sophie Lebret (IGAS)")


class TestLooksLikeSummary:
    def test_accepte_une_phrase(self):
        assert looks_like_summary(RESUME_REEL)

    def test_refuse_une_liste_de_noms(self):
        """Les pages de rapports de l'Igas mettent leurs auteurs en og:description."""
        assert not looks_like_summary(LISTE_DE_NOMS)

    def test_accepte_un_resume_riche_en_noms_propres(self):
        texte = ("Une enquête de Which?, la plus grande organisation de consommateurs du "
                 "Royaume-Uni, a identifié des produits vendus sur Amazon, AliExpress et eBay")
        assert looks_like_summary(texte)

    @pytest.mark.parametrize("texte", [
        "Publié le 25/08/2026 | Temps de lecture : 2 minutes",
        "Trop court",
        "",
    ])
    def test_refuse_les_fragments_de_navigation(self, texte):
        assert not looks_like_summary(texte)


class StubReponse:
    def __init__(self, html: str):
        self.text = html

    def raise_for_status(self) -> None:
        return None


class StubSession:
    def __init__(self, html: str):
        self.html = html
        self.urls: list[str] = []

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        return StubReponse(self.html)


class SessionEnPanne:
    def get(self, *a, **kw):
        raise ConnectionError("hôte injoignable")


def page(corps: str, metas: str = "") -> str:
    return f"<html><head>{metas}</head><body>{corps}</body></html>"


class TestDescribeArticle:
    def test_prefere_la_meta_de_partage(self):
        html = page("<article><p>" + RESUME_REEL + "</p></article>",
                    f'<meta property="og:description" content="{RESUME_REEL}">')
        assert describe_article(StubSession(html), "https://exemple.fr/a", 10) == RESUME_REEL

    def test_se_replie_sur_le_premier_paragraphe_utile(self):
        """Cas Igas : la meta contient les auteurs, le résumé est plus bas."""
        corps = (f"<article><p>Publié le 25/08/2026</p><p>{LISTE_DE_NOMS}</p>"
                 f"<p>{RESUME_REEL}</p></article>")
        html = page(corps, f'<meta name="description" content="{LISTE_DE_NOMS}">')
        assert describe_article(StubSession(html), "https://exemple.fr/a", 10) == RESUME_REEL

    def test_ignore_la_navigation_et_le_pied_de_page(self):
        corps = (f"<nav><p>{RESUME_REEL}</p></nav><footer><p>{RESUME_REEL}</p></footer>"
                 "<article><p>Un résumé bien à lui, dans le corps de l'article publié ici.</p></article>")
        assert describe_article(StubSession(page(corps)), "https://exemple.fr/a", 10).startswith("Un résumé")

    def test_retire_la_mention_wordpress_de_la_meta(self):
        mention = "L’article Un titre est apparu en premier sur Un site ."
        html = page(f"<article><p>{RESUME_REEL}</p></article>",
                    f'<meta property="og:description" content="{mention}">')
        assert describe_article(StubSession(html), "https://exemple.fr/a", 10) == RESUME_REEL

    def test_rend_vide_quand_la_page_n_a_rien(self):
        html = page("<article><p>Trop court</p></article>")
        assert describe_article(StubSession(html), "https://exemple.fr/a", 10) == ""

    def test_laisse_remonter_une_erreur_reseau(self):
        with pytest.raises(ConnectionError):
            describe_article(SessionEnPanne(), "https://exemple.fr/a", 10)
