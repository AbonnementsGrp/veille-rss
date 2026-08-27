"""Nettoyage des textes : balisage, échappement, mentions de flux."""

from __future__ import annotations

import pytest

from veille.text import clean_summary, clean_text, strip_markup


class TestStripMarkup:
    def test_retire_les_balises(self):
        assert strip_markup("<p>Bonjour <strong>le monde</strong></p>") == "Bonjour le monde"

    def test_retire_le_balisage_doublement_echappe(self):
        """Cas ADN : le flux publie &amp;lt;br&amp;gt; dans son résumé.

        Un seul passage rendait "<br>" visible à l'écran du lecteur.
        """
        assert strip_markup("Didier &amp;lt;br&amp;gt; Leprince") == "Didier Leprince"

    def test_preserve_un_chevron_isole(self):
        assert strip_markup("les enfants de moins de 3 ans") == "les enfants de moins de 3 ans"
        assert "<" in strip_markup("comparaison a < b sans balise")

    def test_tolere_un_texte_sans_balisage(self):
        assert strip_markup("Texte simple") == "Texte simple"


class TestCleanSummary:
    BOILERPLATE_FR = ("L’article Alerte sur 150 produits pour bébés est apparu en premier "
                      "sur Les pros de la petite enfance .")
    BOILERPLATE_EN = "The post Les visages d’ADN Tourisme appeared first on ADN Tourisme ."

    def test_rend_vide_quand_seule_la_mention_wordpress_est_presente(self):
        assert clean_summary(self.BOILERPLATE_FR) == ""
        assert clean_summary(self.BOILERPLATE_EN) == ""

    def test_conserve_l_extrait_et_retire_la_mention(self):
        texte = ("Sur les navires de recherche, artistes et scientifiques embarquent ensemble. "
                 + self.BOILERPLATE_FR)
        resultat = clean_summary(texte)
        assert resultat.startswith("Sur les navires de recherche")
        assert "apparu en premier" not in resultat

    def test_ne_touche_pas_a_un_resume_normal(self):
        texte = "Plus de 1 500 téléphones grave danger restent sans bénéficiaire."
        assert clean_summary(texte) == texte

    def test_nettoie_aussi_le_balisage(self):
        assert clean_summary("<p>Un <em>résumé</em> normal et suffisamment long</p>") == (
            "Un résumé normal et suffisamment long")

    @pytest.mark.parametrize("value", ["", None])
    def test_tolere_l_absence_de_valeur(self, value):
        assert clean_summary(value) == ""


class TestCleanText:
    def test_compacte_les_espaces(self):
        assert clean_text("trop   d'espaces\n\tet de tabulations") == "trop d'espaces et de tabulations"

    def test_tronque_a_la_limite(self):
        assert len(clean_text("a" * 5000, limit=100)) == 100

    def test_conserve_la_mention_wordpress(self):
        """clean_text ne juge pas du contenu : seul clean_summary retire la mention."""
        assert "apparu en premier" in clean_text(TestCleanSummary.BOILERPLATE_FR)
