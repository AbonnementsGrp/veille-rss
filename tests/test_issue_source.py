"""Traitement d'une demande de source déposée par formulaire d'issue."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import requests

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


# Page servie par adaptation-changement-climatique.gouv.fr (module Drupal botbuster)
# à tout client qui n'exécute pas son JavaScript, avec le code 503.
VERIFICATION_NAVIGATEUR = """<!DOCTYPE html>
<html><head><title>Vérification du navigateur</title></head>
<body><div class="container"><h2>Vérification du navigateur</h2>
<p>Cette étape nous permet de nous protéger contre des attaques DDOS et autres consultations
excessives par des bots, pour le confort de nos visiteurs légitimes</p></div></body></html>"""


def reponse(code: int, raison: str, html: str, url: str = "https://www.exemple.fr/actualites/") -> requests.Response:
    r = requests.Response()
    r.status_code, r.reason, r.url, r.encoding = code, raison, url, "utf-8"
    r._content = html.encode("utf-8")
    return r


def erreur_http(code: int, raison: str, html: str) -> requests.HTTPError:
    """L'erreur que lève `raise_for_status`, réponse jointe."""
    try:
        reponse(code, raison, html).raise_for_status()
    except requests.HTTPError as exc:
        return exc
    raise AssertionError(f"le code {code} aurait dû lever une erreur")


class TestEchecEnquete:
    URL = "https://www.exemple.fr/actualites/"

    @pytest.mark.parametrize("code", [403, 429, 503])
    def test_une_page_refusee_au_robot_oriente_vers_le_flux_rss(self, code):
        texte = issue_source.echec_enquete(self.URL, erreur_http(code, "Refus", VERIFICATION_NAVIGATEUR))
        assert f"code {code}" in texte and "« Vérification du navigateur »" in texte
        assert "flux RSS" in texte
        # L'adresse est bonne : inviter à la vérifier enverrait le demandeur dans une impasse.
        assert "Vérifiez l'adresse" not in texte

    def test_une_page_introuvable_reste_une_adresse_a_verifier(self):
        texte = issue_source.echec_enquete(self.URL, erreur_http(404, "Not Found", "<title>Page introuvable</title>"))
        assert "Vérifiez l'adresse" in texte and "flux RSS" not in texte

    def test_une_erreur_reseau_garde_son_detail(self):
        texte = issue_source.echec_enquete(self.URL, requests.ConnectionError("nom d'hôte inconnu"))
        assert "nom d'hôte inconnu" in texte and "Vérifiez l'adresse" in texte


class SessionRefusee:
    """Un site qui répond à toute page par sa vérification anti-robots."""

    def get(self, url, timeout=None, allow_redirects=True):
        return reponse(503, "Service Unavailable", VERIFICATION_NAVIGATEUR, url)


class TestMainPageRefusee:
    def test_commente_le_refus_et_conclut_en_erreur(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ISSUE_BODY", CORPS)
        monkeypatch.setattr(issue_source, "load_config", lambda: {"settings": {}, "sites": []})
        monkeypatch.setattr(issue_source, "request_session", lambda settings: SessionRefusee())
        assert issue_source.main(["enquete"]) == 1
        assert (tmp_path / "verdict.txt").read_text(encoding="utf-8") == "erreur"
        commentaire = (tmp_path / "commentaire.md").read_text(encoding="utf-8")
        assert "« Vérification du navigateur »" in commentaire and "flux RSS" in commentaire
