"""Résumé lu sur la page d'un article, quand le flux n'en fournit pas."""

from __future__ import annotations

import pytest

from veille.enrich import article_metadata, describe_article, looks_like_summary, looks_like_title

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


TITRE = "Handicap : l'Anap outille la transformation vers une offre de services coordonnés"


class TestArticleMetadata:
    def test_rend_le_titre_de_partage_et_le_resume(self):
        html = page("", f'<title>Site de l\'Anap</title><meta property="og:title" content="{TITRE}">'
                        f'<meta property="og:description" content="{RESUME_REEL}">')
        assert article_metadata(StubSession(html), "https://exemple.fr/a", 10) == (TITRE, RESUME_REEL)

    def test_ne_prend_jamais_le_titre_de_la_balise_title(self):
        """Sur un site en JavaScript, <title> porte le nom du site, pas celui de l'article."""
        html = page("", f"<title>{TITRE}</title>")
        assert article_metadata(StubSession(html), "https://exemple.fr/a", 10) == ("", "")

    def test_se_replie_sur_le_titre_twitter(self):
        html = page("", f'<meta name="twitter:title" content="{TITRE}">')
        assert article_metadata(StubSession(html), "https://exemple.fr/a", 10)[0] == TITRE

    @pytest.mark.parametrize("titre", ["ANAP", "Court", "TOUT EN CAPITALES"])
    def test_ecarte_un_titre_douteux(self, titre):
        html = page("", f'<meta property="og:title" content="{titre}">')
        assert article_metadata(StubSession(html), "https://exemple.fr/a", 10)[0] == ""
        assert not looks_like_title(titre)

    def test_nettoie_le_titre(self):
        html = page("", '<meta property="og:title" content="  Un   titre &amp; des espaces  ">')
        assert article_metadata(StubSession(html), "https://exemple.fr/a", 10)[0] == "Un titre & des espaces"


TRONQUE = "Handicap : l'Anap outille la transformation vers une offre d"
ENTIER = "Handicap : l'Anap outille la transformation vers une offre de services coordonnés"


class TestCompleteTitle:
    """Salesforce coupe og:title à soixante caractères ; l'en-tête garde le titre entier."""

    def _page(self, og: str, corps: str) -> str:
        return page(corps, f'<meta property="og:title" content="{og}">')

    def test_prolonge_un_titre_coupe_avec_l_en_tete_de_l_article(self):
        corps = (f'<div class="anap-detail-header--top-title">{ENTIER}</div>'
                 f'<div class="anap-detail-header">{ENTIER} 8 décembre 2025</div>')
        assert article_metadata(StubSession(self._page(TRONQUE, corps)), "https://exemple.fr/a", 10)[0] == ENTIER

    def test_accepte_aussi_un_titre_h1(self):
        assert article_metadata(StubSession(self._page(TRONQUE, f"<h1>{ENTIER}</h1>")), "https://exemple.fr/a", 10)[0] == ENTIER

    def test_garde_le_titre_coupe_si_rien_ne_le_prolonge(self):
        corps = "<h1>Un autre titre sans rapport avec le premier</h1>"
        assert article_metadata(StubSession(self._page(TRONQUE, corps)), "https://exemple.fr/a", 10)[0] == TRONQUE

    def test_ne_touche_pas_a_un_titre_complet(self):
        complet = "Réorienter depuis les urgences : vers la bonne filière de soin."
        corps = f"<h1>{complet} Le sous-titre qui suit ne doit pas être ajouté</h1>"
        assert article_metadata(StubSession(self._page(complet, corps)), "https://exemple.fr/a", 10)[0] == complet

    def test_ne_touche_pas_a_un_titre_court(self):
        court = "Webinaire RH « Gestion du temps »"
        corps = f"<h1>{court} et de la présence des équipes</h1>"
        assert article_metadata(StubSession(self._page(court, corps)), "https://exemple.fr/a", 10)[0] == court

    def test_ignore_un_prolongement_demesure(self):
        corps = f'<div class="title">{ENTIER} {"blabla " * 40}</div>'
        assert article_metadata(StubSession(self._page(TRONQUE, corps)), "https://exemple.fr/a", 10)[0] == TRONQUE
