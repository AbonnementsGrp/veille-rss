"""Ordre d'affichage des sources : domaines puis sources, alphabétiques, « Autres » en dernier."""

from __future__ import annotations

from veille.config import display_name, ordered_sites, sort_key, theme_of


def cfg(sites):
    return {"settings": {"themes": ["Culture", "Enfance & Éducation", "Santé, social & séniors"]}, "sites": sites}


def source(name, theme=None, short_name=None):
    site = {"name": name, "url": f"https://exemple.fr/{name}"}
    if theme:
        site["theme"] = theme
    if short_name:
        site["short_name"] = short_name
    return site


def noms(sites):
    return [s["name"] for s in sites]


class TestSortKey:
    def test_ignore_la_casse(self):
        assert sort_key("Zoo") > sort_key("abeille")

    def test_ignore_les_accents(self):
        assert sort_key("Éducation") == sort_key("education")
        assert sort_key("école") < sort_key("Zoo")

    def test_classe_les_domaines_reels_comme_attendu(self):
        domaines = ["Tourisme", "Santé, social & séniors", "Enfance & Éducation", "Restauration", "Culture"]
        assert sorted(domaines, key=sort_key) == [
            "Culture", "Enfance & Éducation", "Restauration", "Santé, social & séniors", "Tourisme"]


class TestThemeOf:
    def test_rend_le_domaine_declare(self):
        assert theme_of({"theme": "Culture"}) == "Culture"

    def test_range_sous_autres_a_defaut(self):
        assert theme_of({}) == "Autres"
        assert theme_of({"theme": "  "}) == "Autres"


class TestDisplayName:
    def test_prefere_le_nom_court(self):
        assert display_name({"name": "CNSA - Actualités", "short_name": "CNSA"}) == "CNSA"

    def test_se_replie_sur_le_nom(self):
        assert display_name({"name": "IGAS"}) == "IGAS"


class TestOrderedSites:
    def test_classe_les_domaines_par_ordre_alphabetique(self):
        sites = [source("t", "Tourisme"), source("c", "Culture"), source("e", "Enfance & Éducation")]
        assert noms(ordered_sites(cfg(sites))) == ["c", "e", "t"]

    def test_l_ordre_de_settings_themes_est_sans_effet(self):
        sites = [source("t", "Tourisme"), source("c", "Culture")]
        config = {"settings": {"themes": ["Tourisme", "Culture"]}, "sites": sites}
        assert noms(ordered_sites(config)) == ["c", "t"]

    def test_classe_les_sources_d_un_domaine_par_nom_affiche(self):
        sites = [
            source("Localtis - Publics fragiles", "Santé", short_name="Localtis — Publics fragiles"),
            source("IGAS", "Santé"),
            source("CNSA - Actualités", "Santé", short_name="CNSA"),
            source("ANAP - Actualités", "Santé", short_name="ANAP"),
        ]
        assert noms(ordered_sites(cfg(sites))) == [
            "ANAP - Actualités", "CNSA - Actualités", "IGAS", "Localtis - Publics fragiles"]

    def test_ignore_casse_et_accents_dans_les_noms(self):
        sites = [source("zèbre", "Culture"), source("Éléphant", "Culture"), source("abeille", "Culture")]
        assert noms(ordered_sites(cfg(sites))) == ["abeille", "Éléphant", "zèbre"]

    def test_autres_passe_en_dernier(self):
        sites = [source("x"), source("t", "Tourisme"), source("a", "Culture")]
        assert noms(ordered_sites(cfg(sites))) == ["a", "t", "x"]

    def test_un_domaine_absent_de_la_liste_prend_sa_place_alphabetique(self):
        sites = [source("s", "Sport"), source("t", "Tourisme"), source("c", "Culture")]
        assert noms(ordered_sites(cfg(sites))) == ["c", "s", "t"]

    def test_deux_sources_de_meme_nom_gardent_l_ordre_du_fichier(self):
        sites = [source("premier", "Culture", short_name="Même nom"), source("second", "Culture", short_name="Même nom")]
        assert noms(ordered_sites(cfg(sites))) == ["premier", "second"]

    def test_n_oublie_aucune_source(self):
        sites = [source(n, t) for n, t in (("a", "Culture"), ("b", None), ("c", "Sport"), ("d", "Enfance & Éducation"))]
        assert len(ordered_sites(cfg(sites))) == 4
