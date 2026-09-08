"""Suppression d'une source : reconnaissance du nom, retrait du bloc, nettoyage."""

from __future__ import annotations

import json

import yaml
import pytest

from veille.sources import apply_removal, find_source, plan_removal, remove_source_block

SITES = [
    {"name": "CNSA - Actualités", "short_name": "CNSA", "theme": "Santé", "url": "https://cnsa.fr/", "output": "cnsa.xml"},
    {"name": "IGAS", "theme": "Santé", "url": "https://igas.gouv.fr/", "output": "igas.xml"},
    {"name": "Localtis - Jeunesse", "short_name": "Localtis — Jeunesse", "theme": "Enfance", "url": "https://l.fr/j"},
    {"name": "Localtis - Publics fragiles", "short_name": "Localtis — Publics fragiles", "theme": "Santé", "url": "https://l.fr/pf"},
]

CONFIG = '''settings:
  themes:
    - "Enfance"
    - "Santé"

sites:
  - name: "CNSA - Actualités"
    short_name: "CNSA"
    theme: "Santé"
    url: "https://cnsa.fr/"
    output: "cnsa.xml"

  - name: "IGAS"
    theme: "Santé"
    url: "https://igas.gouv.fr/"
    # commentaire interne au bloc IGAS
    output: "igas.xml"

  - name: "Localtis - Jeunesse"
    theme: "Enfance"
    url: "https://l.fr/j"
    output: "localtis-j.xml"
'''


class TestFindSource:
    def test_par_nom_complet(self):
        assert find_source("IGAS", SITES)["name"] == "IGAS"

    def test_par_nom_court(self):
        assert find_source("CNSA", SITES)["name"] == "CNSA - Actualités"

    def test_sans_egard_a_la_casse_ni_aux_accents(self):
        assert find_source("cnsa - actualites", SITES)["name"] == "CNSA - Actualités"
        assert find_source("localtis — publics fragiles", SITES)["name"] == "Localtis - Publics fragiles"

    def test_refuse_un_nom_inconnu_en_listant_les_sources(self):
        with pytest.raises(ValueError, match="aucune source nommée « ANAP ».*CNSA"):
            find_source("ANAP", SITES)

    def test_refuse_une_saisie_vide(self):
        with pytest.raises(ValueError, match="aucun nom"):
            find_source("   ", SITES)


class TestRemoveSourceBlock:
    def test_retire_un_bloc_du_milieu_sans_toucher_aux_autres(self):
        resultat = remove_source_block(CONFIG, "IGAS")
        relu = yaml.safe_load(resultat)
        assert [s["name"] for s in relu["sites"]] == ["CNSA - Actualités", "Localtis - Jeunesse"]
        assert relu["settings"]["themes"] == ["Enfance", "Santé"]
        assert "# commentaire interne au bloc IGAS" not in resultat
        assert "\n\n\n" not in resultat, "pas de double saut de ligne laissé derrière"

    def test_retire_le_dernier_bloc_et_termine_proprement(self):
        resultat = remove_source_block(CONFIG, "Localtis - Jeunesse")
        assert yaml.safe_load(resultat)["sites"][-1]["name"] == "IGAS"
        assert resultat.endswith('output: "igas.xml"\n')

    def test_retire_le_premier_bloc(self):
        resultat = remove_source_block(CONFIG, "CNSA - Actualités")
        assert [s["name"] for s in yaml.safe_load(resultat)["sites"]] == ["IGAS", "Localtis - Jeunesse"]
        assert "sites:\n  - name: \"IGAS\"" in resultat

    def test_respecte_les_fins_de_ligne_windows(self):
        crlf = CONFIG.replace("\n", "\r\n")
        resultat = remove_source_block(crlf, "IGAS")
        assert "\r\n" in resultat
        assert "\n" not in resultat.replace("\r\n", ""), "aucune fin de ligne Unix ne doit s'être glissée"
        assert [s["name"] for s in yaml.safe_load(resultat)["sites"]] == ["CNSA - Actualités", "Localtis - Jeunesse"]

    def test_refuse_un_bloc_introuvable(self):
        with pytest.raises(ValueError, match="introuvable"):
            remove_source_block(CONFIG, "ANAP")


class TestPlanRemoval:
    def test_decrit_ce_qui_serait_retire(self, tmp_path):
        (tmp_path / "igas.xml").write_text("<rss/>", encoding="utf-8")
        cfg = {"settings": {}, "sites": SITES}
        history = {"a": {"source": "IGAS"}, "b": {"source": "IGAS"}, "c": {"source": "CNSA - Actualités"}}
        plan = plan_removal("igas", cfg, history, tmp_path)
        assert plan.name == "IGAS" and plan.output == "igas.xml"
        assert plan.history_entries == 2 and plan.feed_exists is True

    def test_deduit_le_fichier_de_sortie_absent_de_la_configuration(self, tmp_path):
        plan = plan_removal("Localtis — Jeunesse", {"settings": {}, "sites": SITES}, {}, tmp_path)
        assert plan.output == "localtis-jeunesse.xml" and plan.feed_exists is False


class TestApplyRemoval:
    def _monde(self, tmp_path):
        config = tmp_path / "sites.yml"
        config.write_text(CONFIG, encoding="utf-8")
        history = tmp_path / "history.json"
        history.write_text(json.dumps({
            "1": {"uid": "1", "source": "IGAS", "title": "A", "link": "https://igas.gouv.fr/a", "first_seen": "2026-08-01T00:00:00+00:00"},
            "2": {"uid": "2", "source": "CNSA - Actualités", "title": "B", "link": "https://cnsa.fr/b", "first_seen": "2026-08-02T00:00:00+00:00"},
        }), encoding="utf-8")
        public = tmp_path / "public"
        public.mkdir()
        (public / "igas.xml").write_text("<rss/>", encoding="utf-8")
        (public / "cnsa.xml").write_text("<rss/>", encoding="utf-8")
        return config, history, public

    def test_retire_la_source_des_trois_endroits(self, tmp_path):
        config, history, public = self._monde(tmp_path)
        cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
        plan = plan_removal("IGAS", cfg, json.loads(history.read_text(encoding="utf-8")), public)
        apply_removal(plan, config, history, public)
        assert [s["name"] for s in yaml.safe_load(config.read_text(encoding="utf-8"))["sites"]] == [
            "CNSA - Actualités", "Localtis - Jeunesse"]
        assert {r["source"] for r in json.loads(history.read_text(encoding="utf-8")).values()} == {"CNSA - Actualités"}
        assert not (public / "igas.xml").exists()
        assert (public / "cnsa.xml").exists(), "les autres flux ne bougent pas"

    def test_tolere_un_flux_deja_absent(self, tmp_path):
        config, history, public = self._monde(tmp_path)
        (public / "igas.xml").unlink()
        cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
        apply_removal(plan_removal("IGAS", cfg, {}, public), config, history, public)
        assert "IGAS" not in config.read_text(encoding="utf-8")


class TestFinsDeLigneSurDisque:
    """Le fichier est relu et réécrit sans traduction : son style de fin de ligne survit."""

    def test_un_fichier_crlf_reste_crlf_apres_suppression(self, tmp_path):
        config = tmp_path / "sites.yml"
        config.write_bytes(CONFIG.replace("\n", "\r\n").encode("utf-8"))
        history = tmp_path / "history.json"
        history.write_text("{}", encoding="utf-8")
        public = tmp_path / "public"
        public.mkdir()
        cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
        apply_removal(plan_removal("IGAS", cfg, {}, public), config, history, public)
        brut = config.read_bytes()
        assert b"\r\n" in brut
        assert b"\n" not in brut.replace(b"\r\n", b"")

    def test_un_fichier_lf_reste_lf_apres_suppression(self, tmp_path):
        config = tmp_path / "sites.yml"
        config.write_bytes(CONFIG.encode("utf-8"))
        history = tmp_path / "history.json"
        history.write_text("{}", encoding="utf-8")
        public = tmp_path / "public"
        public.mkdir()
        cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
        apply_removal(plan_removal("IGAS", cfg, {}, public), config, history, public)
        assert b"\r" not in config.read_bytes(), "aucun retour chariot ne doit apparaître sur un fichier Unix"
