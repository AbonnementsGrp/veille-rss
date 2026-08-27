"""Historique : migration des dates, tri, persistance."""

from __future__ import annotations

import json

from veille.history import (
    history_items_for_source,
    load_history,
    normalize_record_dates,
    save_history,
)


def _record(uid, source, published, titre="Un titre", first_seen="2026-07-20T14:57:50+00:00"):
    return {
        "uid": uid,
        "source": source,
        "title": titre,
        "link": f"https://exemple.fr/{uid}",
        "description": "",
        "published": published,
        "first_seen": first_seen,
    }


class TestNormalizeRecordDates:
    def test_convertit_le_rfc_822_herite(self):
        record = normalize_record_dates(_record("a", "S", "Mon, 13 Jul 2026 08:42:08 +0000"))
        assert record["published"] == "2026-07-13T08:42:08+00:00"

    def test_laisse_une_date_iso_intacte(self):
        record = normalize_record_dates(_record("a", "S", "2026-07-10T14:26:58+00:00"))
        assert record["published"] == "2026-07-10T14:26:58+00:00"

    def test_tolere_les_champs_absents(self):
        assert normalize_record_dates({"uid": "a"}) == {"uid": "a"}


class TestLoadHistory:
    def test_migre_le_fichier_a_la_lecture(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text(json.dumps({
            "a": _record("a", "S", "Mon, 13 Jul 2026 08:42:08 +0000"),
            "b": _record("b", "S", "2026-07-10T14:26:58+00:00"),
        }), encoding="utf-8")
        history = load_history(path)
        assert history["a"]["published"] == "2026-07-13T08:42:08+00:00"
        assert history["b"]["published"] == "2026-07-10T14:26:58+00:00"

    def test_rend_un_historique_vide_si_le_fichier_manque(self, tmp_path):
        assert load_history(tmp_path / "absent.json") == {}

    def test_rend_un_historique_vide_si_le_fichier_est_illisible(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text("{ ceci n'est pas du json", encoding="utf-8")
        assert load_history(path) == {}

    def test_ignore_une_racine_qui_n_est_pas_un_objet(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text("[]", encoding="utf-8")
        assert load_history(path) == {}


class TestSaveHistory:
    def test_conserve_les_entrees_les_plus_recemment_vues(self, tmp_path):
        path = tmp_path / "sous-dossier" / "history.json"
        history = {
            "vieux": _record("vieux", "S", "", first_seen="2026-01-01T00:00:00+00:00"),
            "recent": _record("recent", "S", "", first_seen="2026-08-01T00:00:00+00:00"),
        }
        save_history(history, limit=1, path=path)
        assert list(json.loads(path.read_text(encoding="utf-8"))) == ["recent"]

    def test_aller_retour_sans_perte(self, tmp_path):
        path = tmp_path / "history.json"
        history = {"a": _record("a", "S", "2026-07-10T14:26:58+00:00")}
        save_history(history, limit=10, path=path)
        assert load_history(path) == history


class TestHistoryItemsForSource:
    def test_filtre_sur_la_source(self):
        history = {
            "a": _record("a", "Source A", "2026-07-10T00:00:00+00:00"),
            "b": _record("b", "Source B", "2026-07-11T00:00:00+00:00"),
        }
        items = history_items_for_source(history, "Source A", 10)
        assert [i.link for i in items] == ["https://exemple.fr/a"]

    def test_trie_malgre_des_formats_de_date_melanges(self):
        history = {
            "rfc": _record("rfc", "S", "Wed, 03 Jun 2026 19:04:18 +0000"),
            "iso": _record("iso", "S", "2026-08-25T10:00:00+00:00"),
        }
        items = history_items_for_source(history, "S", 10)
        assert [i.link for i in items] == ["https://exemple.fr/iso", "https://exemple.fr/rfc"]

    def test_respecte_la_limite(self):
        history = {str(n): _record(str(n), "S", f"2026-07-{n:02d}T00:00:00+00:00") for n in range(1, 11)}
        assert len(history_items_for_source(history, "S", 3)) == 3

    def test_ecarte_les_entrees_incompletes(self):
        history = {
            "ok": _record("ok", "S", "2026-07-10T00:00:00+00:00"),
            "sans_titre": {**_record("sans_titre", "S", ""), "title": ""},
            "sans_lien": {**_record("sans_lien", "S", ""), "link": ""},
        }
        assert len(history_items_for_source(history, "S", 10)) == 1
