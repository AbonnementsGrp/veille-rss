"""Ordre d'affichage des sources : domaine, puis `order`, puis le fichier."""

from __future__ import annotations

from veille.config import ordered_sites, theme_of

THEMES = ["Enfance & Éducation", "Santé, social & séniors", "Culture"]


def cfg(sites, themes=THEMES):
    return {"settings": {"themes": themes}, "sites": sites}


def source(name, theme=None, order=None):
    site = {"name": name, "url": f"https://exemple.fr/{name}"}
    if theme:
        site["theme"] = theme
    if order is not None:
        site["order"] = order
    return site


class TestThemeOf:
    def test_rend_le_domaine_declare(self):
        assert theme_of({"theme": "Culture"}) == "Culture"

    def test_range_sous_autres_a_defaut(self):
        assert theme_of({}) == "Autres"
        assert theme_of({"theme": "  "}) == "Autres"


class TestOrderedSites:
    def test_suit_l_ordre_des_domaines(self):
        sites = [source("c", "Culture"), source("a", "Enfance & Éducation")]
        assert [s["name"] for s in ordered_sites(cfg(sites))] == ["a", "c"]

    def test_conserve_l_ordre_du_fichier_dans_un_domaine(self):
        sites = [source(n, "Culture") for n in ("a", "b", "c")]
        assert [s["name"] for s in ordered_sites(cfg(sites))] == ["a", "b", "c"]

    def test_la_cle_order_prime_sur_le_fichier(self):
        sites = [source("a", "Culture", order=2), source("b", "Culture", order=1)]
        assert [s["name"] for s in ordered_sites(cfg(sites))] == ["b", "a"]

    def test_un_domaine_inconnu_passe_en_dernier(self):
        sites = [source("x", "Sport"), source("a", "Culture")]
        assert [s["name"] for s in ordered_sites(cfg(sites))] == ["a", "x"]

    def test_une_source_sans_domaine_passe_en_dernier(self):
        sites = [source("x"), source("a", "Culture")]
        assert [s["name"] for s in ordered_sites(cfg(sites))] == ["a", "x"]

    def test_sans_liste_de_domaines_l_ordre_du_fichier_est_conserve(self):
        sites = [source("b", "Culture"), source("a", "Enfance & Éducation")]
        assert [s["name"] for s in ordered_sites(cfg(sites, themes=[]))] == ["b", "a"]

    def test_n_oublie_aucune_source(self):
        sites = [source(n, t) for n, t in
                 (("a", "Culture"), ("b", None), ("c", "Sport"), ("d", "Enfance & Éducation"))]
        assert len(ordered_sites(cfg(sites))) == 4
