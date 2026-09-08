"""Traitement d'une demande de source déposée par formulaire d'issue."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from veille.models import Item
from veille.onboarding import VERDICT_A_VERIFIER, VERDICT_MANUEL, VERDICT_OK, Proposal

# Le script vit dans scripts/, hors du package : on le charge par son chemin.
SPEC = importlib.util.spec_from_file_location(
    "issue_source", Path(__file__).resolve().parents[1] / "scripts" / "issue_source.py")
issue_source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(issue_source)

CORPS = """### Adresse de la page d'actualités

https://www.exemple.fr/actualites/

### Domaine

Culture

### Nom de la source

_No response_

### Nom court

Exemple

### Pourquoi cette source ?

Parce que.
"""


class TestParseIssueBody:
    def test_lit_chaque_champ_du_formulaire(self):
        champs = issue_source.parse_issue_body(CORPS)
        assert champs["url"] == "https://www.exemple.fr/actualites/"
        assert champs["domaine"] == "Culture"
        assert champs["court"] == "Exemple"
        assert champs["pourquoi"] == "Parce que."

    def test_un_champ_laisse_vide_devient_une_chaine_vide(self):
        assert issue_source.parse_issue_body(CORPS)["nom"] == ""

    def test_ignore_un_libelle_inconnu(self):
        champs = issue_source.parse_issue_body("### Autre chose\n\nvaleur\n")
        assert champs == {}

    def test_tolere_un_corps_vide(self):
        assert issue_source.parse_issue_body("") == {}


def proposition(verdict, warnings=(), items=None):
    return Proposal(
        url="https://www.exemple.fr/actualites/", name="Exemple", short_name="Ex", theme="Culture",
        output="exemple.xml", official_feed="https://www.exemple.fr/feed/", method="flux détecté",
        items=items if items is not None else [
            Item("Exemple", "Un titre | avec barre", "https://www.exemple.fr/a", published="2026-08-25T10:00:00+00:00")],
        verdict=verdict, warnings=list(warnings),
    )


class TestCommentaire:
    def test_annonce_le_verdict_et_la_configuration(self):
        texte = issue_source.commentaire(proposition(VERDICT_OK))
        assert texte.startswith("### ✅")
        assert '- name: "Exemple"' in texte
        assert "pose l'étiquette **approuvé**" in texte

    def test_liste_les_reserves(self):
        texte = issue_source.commentaire(proposition(VERDICT_A_VERIFIER, ["pas de dates"]))
        assert "### ⚠️" in texte and "- pas de dates" in texte

    def test_explique_le_verdict_manuel(self):
        texte = issue_source.commentaire(proposition(VERDICT_MANUEL, items=[]))
        assert "### ❌" in texte and "réglage" in texte and "approuvé" not in texte.split("###")[1].lower()

    def test_protege_le_tableau_markdown(self):
        texte = issue_source.commentaire(proposition(VERDICT_OK))
        assert "Un titre \\| avec barre" in texte

    def test_confirme_l_ajout(self):
        assert "Source ajoutée" in issue_source.commentaire(proposition(VERDICT_OK), ajoutee=True)


class TestMainSansAdresse:
    def test_refuse_un_formulaire_sans_url(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", "### Domaine\n\nCulture\n")
        assert issue_source.main(["enquete"]) == 1
        assert (tmp_path / "verdict.txt").read_text(encoding="utf-8") == "erreur"
        assert "adresse valide" in (tmp_path / "commentaire.md").read_text(encoding="utf-8")

    def test_refuse_une_adresse_sans_protocole(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", "### Adresse de la page d'actualités\n\nwww.exemple.fr\n")
        assert issue_source.main(["enquete"]) == 1
