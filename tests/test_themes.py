"""Domaines : validation, insertion dans les deux fichiers, cohérence."""

from __future__ import annotations

import yaml
import pytest

from veille.themes import (
    FORM_PATH,
    add_theme,
    current_themes,
    form_themes,
    insert_list_item,
    plan_theme,
)

THEMES = ["Enfance & Éducation", "Santé, social & séniors", "Culture"]

CONFIG = '''settings:
  merged_output: "veille.xml"
  # Ordre d'affichage des domaines.
  themes:
    - "Enfance & Éducation"
    - "Santé, social & séniors"
    - "Culture"
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
        - "Enfance & Éducation"
        - "Santé, social & séniors"
        - "Culture"
    validations:
      required: true
  - type: input
    id: nom
    attributes:
      label: Nom
'''


class TestPlanTheme:
    def test_place_en_dernier_par_defaut(self):
        plan = plan_theme("Logement", themes=THEMES)
        assert plan.result == THEMES + ["Logement"] and plan.position == 4

    def test_place_apres_un_domaine_donne(self):
        plan = plan_theme("Logement", after="culture", themes=THEMES)
        assert plan.result == THEMES + ["Logement"]
        plan = plan_theme("Logement", after="Enfance & Éducation", themes=THEMES)
        assert plan.result[1] == "Logement" and plan.after == "Enfance & Éducation"

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

    def test_refuse_un_domaine_de_reference_inconnu(self):
        with pytest.raises(ValueError, match="aucun domaine « Sport »"):
            plan_theme("Logement", after="Sport", themes=THEMES)


class TestInsertListItem:
    def test_insere_en_fin_de_liste_sans_toucher_au_reste(self):
        lignes = CONFIG.split("\n")
        entete = next(i for i, l in enumerate(lignes) if l.strip() == "themes:")
        resultat = insert_list_item(CONFIG, entete, "Logement")
        assert yaml.safe_load(resultat)["settings"]["themes"] == THEMES + ["Logement"]
        assert "# Ordre d'affichage des domaines." in resultat
        assert yaml.safe_load(resultat)["settings"]["request_timeout"] == 30

    def test_insere_apres_un_element(self):
        lignes = CONFIG.split("\n")
        entete = next(i for i, l in enumerate(lignes) if l.strip() == "themes:")
        resultat = insert_list_item(CONFIG, entete, "Logement", after="Enfance & Éducation")
        assert yaml.safe_load(resultat)["settings"]["themes"][1] == "Logement"

    def test_reprend_l_indentation_des_elements(self):
        lignes = CONFIG.split("\n")
        entete = next(i for i, l in enumerate(lignes) if l.strip() == "themes:")
        resultat = insert_list_item(CONFIG, entete, "Logement")
        assert '    - "Logement"' in resultat.split("\n")

    def test_refuse_une_liste_absente(self):
        with pytest.raises(ValueError):
            insert_list_item("settings:\n  themes:\n  autre: 1\n", 1, "X")


class TestAddTheme:
    def _fichiers(self, tmp_path, form=FORM):
        config = tmp_path / "sites.yml"
        formulaire = tmp_path / "nouvelle-source.yml"
        config.write_text(CONFIG, encoding="utf-8")
        formulaire.write_text(form, encoding="utf-8")
        return config, formulaire

    def test_ecrit_le_domaine_aux_deux_endroits(self, tmp_path):
        config, formulaire = self._fichiers(tmp_path)
        add_theme(plan_theme("Logement", themes=THEMES), config, formulaire)
        assert current_themes(config) == THEMES + ["Logement"]
        assert form_themes(formulaire) == THEMES + ["Logement"]

    def test_respecte_la_place_demandee_dans_les_deux_fichiers(self, tmp_path):
        config, formulaire = self._fichiers(tmp_path)
        add_theme(plan_theme("Logement", after="Culture", themes=THEMES), config, formulaire)
        assert current_themes(config)[-1] == "Logement" == form_themes(formulaire)[-1]

    def test_preserve_le_reste_des_fichiers(self, tmp_path):
        config, formulaire = self._fichiers(tmp_path)
        add_theme(plan_theme("Logement", themes=THEMES), config, formulaire)
        assert "# Ordre d'affichage des domaines." in config.read_text(encoding="utf-8")
        assert yaml.safe_load(formulaire.read_text(encoding="utf-8"))["body"][1]["id"] == "nom"

    def test_refuse_si_le_formulaire_a_derive(self, tmp_path):
        config, formulaire = self._fichiers(tmp_path, form=FORM.replace('        - "Culture"\n', ""))
        with pytest.raises(ValueError, match="diffère"):
            add_theme(plan_theme("Logement", themes=THEMES), config, formulaire)
        assert current_themes(config) == THEMES, "rien ne doit être écrit en cas de refus"


class TestCoherenceDuDepot:
    """Les deux listes réelles doivent rester identiques : c'est ce que l'outil garantit."""

    def test_le_formulaire_offre_exactement_les_domaines_configures(self):
        assert form_themes(FORM_PATH) == current_themes()
