"""Traitement d'une demande de suppression de domaine déposée par formulaire d'issue."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from veille.issues import parse_form
from veille.themes import plan_theme_removal

SPEC = importlib.util.spec_from_file_location(
    "issue_supprimer_domaine", Path(__file__).resolve().parents[1] / "scripts" / "issue_supprimer_domaine.py")
issue_supprimer_domaine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(issue_supprimer_domaine)

THEMES = ["Culture", "Enfance & Éducation", "Tourisme"]
SITES = [
    {"name": "ADN Tourisme", "theme": "Tourisme", "url": "https://adn.fr/"},
    {"name": "Observatoire de la culture", "short_name": "Observatoire", "theme": "Culture", "url": "https://obs.fr/"},
]
CORPS = """### Domaine à supprimer

tourisme

### Rattacher ses sources à

_No response_

### Pourquoi le supprimer ?

Plus personne ne le suit.
"""


class TestLectureDuFormulaire:
    def test_les_libelles_du_formulaire_sont_ceux_du_script(self):
        assert parse_form(CORPS, issue_supprimer_domaine.CHAMPS) == {
            "domaine": "tourisme", "cible": "", "pourquoi": "Plus personne ne le suit."}


class TestCommentaire:
    def test_annonce_les_sources_deplacees_sous_autres_et_la_consigne(self):
        texte = issue_supprimer_domaine.commentaire(plan_theme_removal("Tourisme", themes=THEMES, sites=SITES))
        assert "**Domaine reconnu** : Tourisme" in texte
        assert "ADN Tourisme" in texte and "sous « Autres »" in texte
        assert "1. Culture" in texte and "2. Enfance & Éducation" in texte and "Tourisme" not in texte.split("restent")[1].split("Aucune")[0]
        assert "Aucune source ni aucun article ne sera supprimé" in texte
        assert "étiquette **approuvé**" in texte

    def test_annonce_le_domaine_de_rattachement(self):
        texte = issue_supprimer_domaine.commentaire(
            plan_theme_removal("Tourisme", "Culture", themes=THEMES, sites=SITES))
        assert "rattachées au domaine **« Culture »**" in texte

    def test_un_domaine_sans_source(self):
        texte = issue_supprimer_domaine.commentaire(
            plan_theme_removal("Enfance & Éducation", themes=THEMES, sites=SITES))
        assert "**Sources concernées** : aucune" in texte

    def test_confirme_la_suppression(self):
        texte = issue_supprimer_domaine.commentaire(
            plan_theme_removal("Tourisme", themes=THEMES, sites=SITES), applique=True)
        assert "Domaine supprimé" in texte
        assert "Aucune source ni aucun article n'a été supprimé" in texte
        assert "approuvé" not in texte


class TestMain:
    def test_refuse_un_domaine_manquant(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", "### Pourquoi le supprimer ?\n\nParce que.\n")
        assert issue_supprimer_domaine.main(["enquete"]) == 1
        assert (tmp_path / "verdict.txt").read_text(encoding="utf-8") == "erreur"
        assert "aucun nom de domaine" in (tmp_path / "commentaire.md").read_text(encoding="utf-8")

    def test_refuse_un_domaine_inconnu_des_domaines_reels(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", "### Domaine à supprimer\n\nSport automobile\n")
        assert issue_supprimer_domaine.main(["enquete"]) == 1
        assert "aucun domaine" in (tmp_path / "commentaire.md").read_text(encoding="utf-8")

    def test_enquete_sur_un_domaine_reel_sans_rien_ecrire(self, tmp_path, monkeypatch):
        # Les domaines réels changent par formulaire : le test prend le premier
        # domaine de la configuration courante qui a au moins une source.
        from veille.config import display_name, load_config, theme_of
        from veille.themes import current_themes
        themes = current_themes()
        site = next(s for s in load_config()["sites"] if theme_of(s) in themes)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", f"### Domaine à supprimer\n\n{theme_of(site).lower()}\n")
        assert issue_supprimer_domaine.main(["enquete"]) == 0
        assert (tmp_path / "verdict.txt").read_text(encoding="utf-8") == "ok"
        commentaire = (tmp_path / "commentaire.md").read_text(encoding="utf-8")
        assert f"**Domaine reconnu** : {theme_of(site)}" in commentaire
        assert display_name(site) in commentaire
