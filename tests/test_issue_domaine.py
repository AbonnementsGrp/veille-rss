"""Traitement d'une demande de domaine déposée par formulaire d'issue."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from veille.themes import plan_theme

SPEC = importlib.util.spec_from_file_location(
    "issue_domaine", Path(__file__).resolve().parents[1] / "scripts" / "issue_domaine.py")
issue_domaine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(issue_domaine)

THEMES = ["Culture", "Enfance & Éducation"]
CORPS = """### Nom du domaine

Logement & Habitat

### Pourquoi ce domaine ?

Pour les sources sur le logement.
"""


class TestParseIssueBody:
    def test_lit_les_champs(self):
        assert issue_domaine.parse_issue_body(CORPS) == {
            "nom": "Logement & Habitat", "pourquoi": "Pour les sources sur le logement."}

    def test_un_champ_vide_devient_une_chaine_vide(self):
        assert issue_domaine.parse_issue_body("### Nom du domaine\n\n_No response_\n")["nom"] == ""

    def test_tolere_un_corps_vide(self):
        assert issue_domaine.parse_issue_body("") == {}


class TestCommentaire:
    def test_montre_la_liste_alphabetique_et_la_consigne(self):
        texte = issue_domaine.commentaire(plan_theme("Logement", themes=THEMES))
        assert "1. Culture" in texte
        assert "3. **Logement** ← nouveau" in texte
        assert "par ordre alphabétique" in texte
        assert "étiquette **approuvé**" in texte

    def test_confirme_l_ajout(self):
        texte = issue_domaine.commentaire(plan_theme("Logement", themes=THEMES), ajoute=True)
        assert "Domaine ajouté" in texte
        assert "approuvé" not in texte


class TestMain:
    def test_refuse_un_nom_manquant(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", "### Pourquoi ce domaine ?\n\nParce que.\n")
        assert issue_domaine.main(["enquete"]) == 1
        assert (tmp_path / "verdict.txt").read_text(encoding="utf-8") == "erreur"
        assert "vide" in (tmp_path / "commentaire.md").read_text(encoding="utf-8")

    def test_refuse_un_doublon_des_domaines_reels(self, tmp_path, monkeypatch):
        # Les domaines réels changent par formulaire : le doublon est pris dans la
        # configuration courante plutôt que figé dans le test.
        from veille.themes import current_themes
        existant = current_themes()[0]
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", f"### Nom du domaine\n\n{existant}\n")
        assert issue_domaine.main(["enquete"]) == 1
        assert "existe déjà" in (tmp_path / "commentaire.md").read_text(encoding="utf-8")

    def test_accepte_un_domaine_nouveau_sans_ecrire(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", CORPS)
        assert issue_domaine.main(["enquete"]) == 0
        assert (tmp_path / "verdict.txt").read_text(encoding="utf-8") == "ok"
        assert "Logement & Habitat" in (tmp_path / "commentaire.md").read_text(encoding="utf-8")
