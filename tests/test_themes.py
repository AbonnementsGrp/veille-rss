"""Domaines : validation, réécriture alphabétique des deux listes, cohérence."""

from __future__ import annotations

import yaml
import pytest

from veille.config import sort_key
from veille.themes import (
    FORM_PATH,
    add_theme,
    current_themes,
    form_themes,
    list_items,
    plan_theme,
    replace_list_items,
    sorted_themes,
)

THEMES = ["Culture", "Enfance & Éducation", "Santé, social & séniors"]

CONFIG = '''settings:
  merged_output: "veille.xml"
  # Domaines reconnus.
  themes:
    - "Culture"
    - "Enfance & Éducation"
    - "Santé, social & séniors"
  request_timeout: 30

sites:
  - name: "A"
    url: "https://a.fr/"
'''

FORM = '''name: Proposer une nouvelle source
body:
  - type: dropdown
    id: domaine
    attributes:
      label: Domaine
      options:
        - "Culture"
        - "Enfance & Éducation"
        - "Santé, social & séniors"
    validations:
      required: true
  - type: input
    id: nom
    attributes:
      label: Nom
'''


def entete(texte, mot):
    return next(i for i, l in enumerate(texte.split("\n")) if l.strip() == mot)


class TestPlanTheme:
    def test_place_le_domaine_a_sa_position_alphabetique(self):
        plan = plan_theme("Logement", themes=THEMES)
        assert plan.result == ["Culture", "Enfance & Éducation", "Logement", "Santé, social & séniors"]
        assert plan.position == 3

    def test_les_accents_ne_perturbent_pas_le_classement(self):
        assert plan_theme("Écoles", themes=THEMES).result[1] == "Écoles"

    def test_trie_aussi_une_liste_de_depart_desordonnee(self):
        plan = plan_theme("Logement", themes=["Tourisme", "Culture"])
        assert plan.result == ["Culture", "Logement", "Tourisme"]

    def test_normalise_les_espaces(self):
        assert plan_theme("  Logement   &  Habitat ", themes=THEMES).name == "Logement & Habitat"

    @pytest.mark.parametrize("nom, motif", [
        ("", "vide"),
        ("x" * 41, "dépasse"),
        ("Autres", "réservé"),
        ("culture", "existe déjà"),
    ])
    def test_refuse_un_nom_invalide(self, nom, motif):
        with pytest.raises(ValueError, match=motif):
            plan_theme(nom, themes=THEMES)


class TestListItems:
    def test_lit_les_elements_de_la_liste(self):
        lignes = CONFIG.split("\n")
        assert [v for _, v in list_items(lignes, entete(CONFIG, "themes:"))] == THEMES

    def test_s_arrete_a_la_fin_de_la_liste(self):
        lignes = CONFIG.split("\n")
        numeros = [n for n, _ in list_items(lignes, entete(CONFIG, "themes:"))]
        assert lignes[max(numeros) + 1].strip().startswith("request_timeout")


class TestReplaceListItems:
    def test_remplace_les_elements_sans_toucher_au_reste(self):
        resultat = replace_list_items(CONFIG, entete(CONFIG, "themes:"), ["A", "B"])
        relu = yaml.safe_load(resultat)
        assert relu["settings"]["themes"] == ["A", "B"]
        assert relu["settings"]["request_timeout"] == 30
        assert "# Domaines reconnus." in resultat
        assert relu["sites"][0]["name"] == "A"

    def test_reprend_l_indentation_des_elements(self):
        resultat = replace_list_items(CONFIG, entete(CONFIG, "themes:"), ["Logement"])
        assert '    - "Logement"' in resultat.split("\n")

    def test_refuse_une_liste_absente(self):
        with pytest.raises(ValueError):
            replace_list_items("settings:\n  themes:\n  autre: 1\n", 1, ["X"])


class TestAddTheme:
    def _fichiers(self, tmp_path, form=FORM):
        config = tmp_path / "sites.yml"
        formulaire = tmp_path / "nouvelle-source.yml"
        config.write_text(CONFIG, encoding="utf-8")
        formulaire.write_text(form, encoding="utf-8")
        return config, formulaire

    def test_ecrit_la_liste_alphabetique_aux_deux_endroits(self, tmp_path):
        config, formulaire = self._fichiers(tmp_path)
        add_theme(plan_theme("Logement", themes=THEMES), config, formulaire)
        attendu = ["Culture", "Enfance & Éducation", "Logement", "Santé, social & séniors"]
        assert current_themes(config) == attendu
        assert form_themes(formulaire) == attendu

    def test_preserve_le_reste_des_fichiers(self, tmp_path):
        config, formulaire = self._fichiers(tmp_path)
        add_theme(plan_theme("Logement", themes=THEMES), config, formulaire)
        assert "# Domaines reconnus." in config.read_text(encoding="utf-8")
        assert yaml.safe_load(formulaire.read_text(encoding="utf-8"))["body"][1]["id"] == "nom"

    def test_tolere_un_ordre_different_mais_pas_un_contenu_different(self, tmp_path):
        desordonne = FORM.replace('        - "Culture"\n        - "Enfance & Éducation"\n',
                                  '        - "Enfance & Éducation"\n        - "Culture"\n')
        config, formulaire = self._fichiers(tmp_path, form=desordonne)
        add_theme(plan_theme("Logement", themes=THEMES), config, formulaire)
        assert form_themes(formulaire) == current_themes(config)

    def test_refuse_si_le_formulaire_a_derive(self, tmp_path):
        config, formulaire = self._fichiers(tmp_path, form=FORM.replace('        - "Culture"\n', ""))
        with pytest.raises(ValueError, match="diffère"):
            add_theme(plan_theme("Logement", themes=THEMES), config, formulaire)
        assert current_themes(config) == THEMES, "rien ne doit être écrit en cas de refus"


class TestCoherenceDuDepot:
    """Ce que l'outil garantit sur les fichiers réels : mêmes domaines, ordre alphabétique."""

    def test_le_formulaire_offre_exactement_les_domaines_configures(self):
        assert form_themes(FORM_PATH) == current_themes()

    def test_les_domaines_sont_ranges_par_ordre_alphabetique(self):
        assert current_themes() == sorted_themes(current_themes())
        assert sorted(current_themes(), key=sort_key) == current_themes()
