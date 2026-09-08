"""Surveillance : silence prolongé, titres de navigation, dates absentes ou futures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from veille.models import Item
from veille.quality import (
    STALE_AFTER_DAYS,
    days_since_last,
    looks_like_navigation,
    quality_warnings,
)

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
SITE = {"name": "S", "url": "https://exemple.fr/actualites/"}


def article(n: int, jours: int | None = 1, titre: str | None = None, lien: str | None = None) -> Item:
    date = (NOW - timedelta(days=jours)).isoformat() if jours is not None else ""
    return Item("S", titre or f"Un vrai titre d'article numéro {n}", lien or f"https://exemple.fr/article-{n}", published=date)


class TestSilence:
    def test_rien_a_signaler_pour_une_source_vivante(self):
        assert quality_warnings([article(1)], [article(1), article(2, 40)], SITE, {}, "flux officiel", NOW) == []

    def test_signale_une_source_sans_nouveaute_depuis_trop_longtemps(self):
        publies = [article(1, 203), article(2, 260)]
        [avertissement] = quality_warnings([], publies, SITE, {}, "flux officiel", NOW)
        assert avertissement == f"rien de neuf depuis 203 jours (seuil : {STALE_AFTER_DAYS})"

    def test_le_seuil_se_regle_globalement_puis_par_source(self):
        publies = [article(1, 74)]
        assert quality_warnings([], publies, SITE, {"stale_after_days": 90}, "flux officiel", NOW) == []
        assert quality_warnings([], publies, SITE, {"stale_after_days": 30}, "flux officiel", NOW)
        lente = {**SITE, "stale_after_days": 120}
        assert quality_warnings([], publies, lente, {"stale_after_days": 30}, "flux officiel", NOW) == []

    def test_le_silence_se_juge_sur_le_flux_publie_historique_compris(self):
        frais = []  # rien collecté aujourd'hui, mais un article d'hier dans l'historique
        assert quality_warnings(frais, [article(1, 1)], SITE, {}, "flux officiel", NOW) == []

    def test_un_article_sans_date_compte_par_sa_decouverte(self):
        item = Item("S", "Un vrai titre d'article", "https://exemple.fr/a", first_seen=(NOW - timedelta(days=2)).isoformat())
        assert days_since_last([item], NOW) == 2
        assert days_since_last([], NOW) is None
        assert days_since_last([Item("S", "T", "https://exemple.fr/a")], NOW) is None

    def test_une_date_future_ne_donne_pas_un_silence_negatif(self):
        assert days_since_last([article(1, -3)], NOW) == 0


class TestDates:
    def test_signale_des_articles_dates_dans_le_futur(self):
        frais = [article(1, -13), article(2, 1), article(3, 2)]
        avertissements = quality_warnings(frais, frais, SITE, {}, "html_selectors", NOW)
        assert "1 article(s) daté(s) dans le futur" in avertissements

    def test_tolere_le_lendemain(self):
        """Fuseaux horaires et publications programmées du jour ne sont pas des erreurs."""
        frais = [article(1, 0), article(2, -0.5), article(3, 1)]
        assert quality_warnings(frais, frais, SITE, {}, "html_selectors", NOW) == []

    def test_signale_une_extraction_sans_aucune_date(self):
        frais = [article(n, None) for n in range(1, 5)]
        avertissements = quality_warnings(frais, frais, SITE, {}, "html_selectors", NOW)
        assert "aucun article daté : ils sont datés du jour de leur découverte" in avertissements

    def test_un_flux_sans_dates_n_est_pas_juge_sur_ce_point(self):
        frais = [article(n, None) for n in range(1, 5)]
        assert quality_warnings(frais, [article(1)], SITE, {}, "flux officiel", NOW) == []


class TestNavigation:
    @pytest.mark.parametrize("titre", ["Accueil", "Contact", "En savoir plus", "Lire la suite »", "Mentions légales",
                                       "Toutes les actualités", "Menu", "FAQ", "Suivant"])
    def test_reconnait_un_libelle_de_menu(self, titre):
        assert looks_like_navigation(Item("S", titre, "https://exemple.fr/x"))

    @pytest.mark.parametrize("lien", ["https://exemple.fr/category/actus/", "https://exemple.fr/tag/emploi",
                                      "https://exemple.fr/actualites/page/2", "https://exemple.fr/actualites/?paged=3",
                                      "https://exemple.fr/author/admin/"])
    def test_reconnait_une_rubrique_ou_une_pagination(self, lien):
        assert looks_like_navigation(Item("S", "Un titre qui a l'air normal pourtant", lien))

    def test_reconnait_un_lien_vers_la_page_suivie_elle_meme(self):
        assert looks_like_navigation(Item("S", "Actualités du réseau", "https://exemple.fr/actualites"),
                                     "https://exemple.fr/actualites/")

    def test_laisse_passer_un_vrai_titre(self):
        assert not looks_like_navigation(Item("S", "Premier référentiel national pour un bloc éco-responsable",
                                              "https://exemple.fr/s/article/referentiel"))
        assert not looks_like_navigation(Item("S", "Loi 2026-1", "https://exemple.fr/loi"), "https://exemple.fr/actualites/")

    def test_signale_une_extraction_qui_ne_ramene_que_le_menu(self):
        frais = [article(1, titre="Accueil"), article(2, titre="Contact"), article(3), article(4)]
        avertissements = quality_warnings(frais, frais, SITE, {}, "html_selectors", NOW)
        assert "2 titre(s) sur 4 ressemblent à des liens de navigation" in avertissements

    def test_un_seul_lien_douteux_sur_beaucoup_ne_declenche_rien(self):
        frais = [article(n) for n in range(1, 10)] + [article(10, titre="Contact")]
        assert quality_warnings(frais, frais, SITE, {}, "generic_links", NOW) == []

    def test_trop_peu_d_articles_pour_juger(self):
        frais = [article(1, titre="Accueil"), article(2, titre="Contact")]
        assert quality_warnings(frais, [article(3)], SITE, {}, "html_selectors", NOW) == []

    @pytest.mark.parametrize("method", ["flux officiel", "flux détecté", "plan de site"])
    def test_le_contenu_tel_que_publie_n_est_pas_juge(self, method):
        frais = [article(1, titre="Accueil"), article(2, titre="Contact"), article(3, titre="Menu")]
        assert quality_warnings(frais, frais, SITE, {}, method, NOW) == []

    @pytest.mark.parametrize("method", ["repli : html_selectors", "navigateur : generic_links", "json_ld+html"])
    def test_toute_extraction_de_page_est_jugee(self, method):
        frais = [article(1, titre="Accueil"), article(2, titre="Contact"), article(3, titre="Menu")]
        assert quality_warnings(frais, frais, SITE, {}, method, NOW)


class TestCumul:
    def test_plusieurs_avertissements_se_cumulent_dans_un_ordre_stable(self):
        frais = [article(n, None, titre="Accueil") for n in range(1, 4)]
        publies = [article(9, 400)]
        avertissements = quality_warnings(frais, publies, SITE, {}, "html_selectors", NOW)
        assert [a.split(" ")[0] for a in avertissements] == ["rien", "3", "aucun"]
