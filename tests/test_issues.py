"""Lecture commune des formulaires d'issue."""

from __future__ import annotations

from veille.issues import APPROBATION, parse_form, refus, write_outputs

CHAMPS = {"Domaine actuel": "ancien", "Nouveau nom": "nouveau", "Pourquoi ce changement ?": "pourquoi"}


class TestParseForm:
    def test_associe_chaque_libelle_a_sa_cle(self):
        corps = "### Domaine actuel\n\nCulture\n\n### Nouveau nom\n\nArts\n\n### Pourquoi ce changement ?\n\n_No response_\n"
        assert parse_form(corps, CHAMPS) == {"ancien": "Culture", "nouveau": "Arts", "pourquoi": ""}

    def test_ignore_les_libelles_inconnus(self):
        assert parse_form("### Autre\n\nvaleur\n", CHAMPS) == {}

    def test_tolere_un_corps_absent(self):
        assert parse_form("", CHAMPS) == {}
        assert parse_form(None, CHAMPS) == {}

    def test_garde_une_valeur_sur_plusieurs_lignes(self):
        corps = "### Pourquoi ce changement ?\n\nPremière ligne.\nSeconde ligne.\n"
        assert parse_form(corps, CHAMPS)["pourquoi"] == "Première ligne.\nSeconde ligne."


class TestSorties:
    def test_ecrit_le_commentaire_et_le_verdict(self, tmp_path):
        write_outputs("bonjour\n", "ok", tmp_path)
        assert (tmp_path / "commentaire.md").read_text(encoding="utf-8") == (
            "bonjour\n\n---\n[← Retour au tableau de bord de la veille](https://abonnementsgrp.github.io/veille-rss/)\n")
        assert (tmp_path / "verdict.txt").read_text(encoding="utf-8") == "ok"

    def test_le_lien_de_retour_n_est_pas_double(self, tmp_path):
        from veille.issues import PIED_DE_PAGE, avec_pied_de_page
        une_fois = avec_pied_de_page("bonjour\n")
        assert avec_pied_de_page(une_fois) == une_fois
        assert une_fois.count("Retour au tableau de bord") == 1
        assert PIED_DE_PAGE.startswith("\n---\n")

    def test_un_refus_explique_et_rend_un_echec(self, tmp_path):
        assert refus("le nom est vide", tmp_path) == 1
        assert "le nom est vide" in (tmp_path / "commentaire.md").read_text(encoding="utf-8")
        assert (tmp_path / "verdict.txt").read_text(encoding="utf-8") == "erreur"

    def test_la_consigne_d_approbation_nomme_l_etiquette(self):
        assert "**approuvé**" in APPROBATION
