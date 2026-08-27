"""Dates : normalisation, lecture et clé de tri."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from veille.dates import EPOCH, item_sort_key, normalize_date, parse_date_for_feed, parse_iso
from veille.models import Item


class TestParseIso:
    @pytest.mark.parametrize("value, attendu", [
        ("2026-07-10T14:26:58+00:00", datetime(2026, 7, 10, 14, 26, 58, tzinfo=timezone.utc)),
        ("2026-07-10T14:26:58Z", datetime(2026, 7, 10, 14, 26, 58, tzinfo=timezone.utc)),
        ("  2026-07-10T14:26:58+00:00  ", datetime(2026, 7, 10, 14, 26, 58, tzinfo=timezone.utc)),
    ])
    def test_lit_les_formats_iso(self, value, attendu):
        assert parse_iso(value) == attendu

    @pytest.mark.parametrize("value", [
        "Wed, 03 Jun 2026 19:04:18 +0000",
        "10/07/2026",
        "pas une date",
        "",
        None,
    ])
    def test_rend_none_hors_iso(self, value):
        assert parse_iso(value) is None


class TestNormalizeDate:
    def test_preserve_une_date_iso_dont_le_jour_peut_passer_pour_un_mois(self):
        """Régression : dayfirst=True lisait "2026-07-10" comme le 10e mois.

        Le bug décalait silencieusement toute date ISO dont le jour est <= 12,
        et faisait apparaître des articles datés du futur en tête de flux.
        """
        assert normalize_date("2026-07-10T14:26:58+00:00") == "2026-07-10T14:26:58+00:00"
        assert normalize_date("2026-03-11T15:44:32+00:00") == "2026-03-11T15:44:32+00:00"

    def test_convertit_le_rfc_822_des_flux(self):
        assert normalize_date("Wed, 03 Jun 2026 19:04:18 +0000") == "2026-06-03T19:04:18+00:00"

    def test_ramene_les_decalages_en_utc(self):
        assert normalize_date("2026-08-25T10:02:53+02:00") == "2026-08-25T08:02:53+00:00"
        assert normalize_date("2026-08-25T10:02:53Z") == "2026-08-25T10:02:53+00:00"

    def test_lit_une_date_francaise_jour_en_premier(self):
        assert normalize_date("10/07/2026").startswith("2026-07-10")

    def test_accepte_datetime_et_struct_time(self):
        assert normalize_date(datetime(2026, 7, 10, tzinfo=timezone.utc)) == "2026-07-10T00:00:00+00:00"
        assert normalize_date((2026, 7, 10, 14, 26, 58, 0, 0, 0)) == "2026-07-10T14:26:58+00:00"

    def test_suppose_utc_si_le_fuseau_manque(self):
        assert normalize_date("2026-07-10T14:26:58") == "2026-07-10T14:26:58+00:00"

    @pytest.mark.parametrize("value", ["", None, "n'importe quoi", [], 0])
    def test_rend_une_chaine_vide_si_illisible(self, value):
        assert normalize_date(value) == ""


class TestParseDateForFeed:
    def test_rend_un_datetime_conscient_du_fuseau(self):
        dt = parse_date_for_feed("2026-07-10T14:26:58+00:00")
        assert dt is not None and dt.tzinfo is not None

    def test_ne_decale_pas_une_date_iso(self):
        assert parse_date_for_feed("2026-07-10T00:00:00+00:00").month == 7

    def test_rend_none_si_illisible(self):
        assert parse_date_for_feed("") is None
        assert parse_date_for_feed("pas une date") is None


class TestItemSortKey:
    def _item(self, **kw):
        return Item(source="S", title="T", link="https://exemple.fr/a", **kw)

    def test_trie_les_formats_melanges_du_plus_recent_au_plus_ancien(self):
        """Régression : le tri comparait des chaînes, donc "Wed, ..." > "2026-...".

        Les entrées RFC-822 héritées de l'historique remontaient toutes en tête
        de flux, quelle que soit leur date réelle.
        """
        recent = self._item(published="2026-08-25T10:00:00+00:00")
        ancien_rfc = self._item(published="Wed, 03 Jun 2026 19:04:18 +0000")
        milieu = self._item(published="2026-07-15T10:00:00+00:00")
        ordre = sorted([ancien_rfc, recent, milieu], key=item_sort_key, reverse=True)
        assert ordre == [recent, milieu, ancien_rfc]

    def test_se_replie_sur_la_date_de_decouverte(self):
        item = self._item(published="", first_seen="2026-08-25T10:00:00+00:00")
        assert item_sort_key(item).day == 25

    def test_place_en_dernier_un_article_sans_date(self):
        sans_date = self._item()
        date = self._item(published="1999-01-01T00:00:00+00:00")
        assert item_sort_key(sans_date) == EPOCH
        assert sorted([sans_date, date], key=item_sort_key, reverse=True) == [date, sans_date]


class TestDatesFrancaises:
    """Les pages d'actualités françaises datent en clair : "25 juin 2026"."""

    @pytest.mark.parametrize("value, attendu", [
        ("25 juin 2026", "2026-06-25"),
        ("1er août 2026", "2026-08-01"),
        ("3 février 2026", "2026-02-03"),
        ("27 févr. 2026", "2026-02-27"),
        ("lundi 3 février 2026", "2026-02-03"),
        ("15 décembre 2025", "2025-12-15"),
        ("1 janvier 2026", "2026-01-01"),
        ("30 septembre 2026", "2026-09-30"),
    ])
    def test_lit_les_mois_en_francais(self, value, attendu):
        assert normalize_date(value).startswith(attendu)

    def test_lit_encore_les_mois_en_anglais(self):
        """Les flux RSS datent en RFC-822 anglais : ne pas le perdre."""
        assert normalize_date("Wed, 03 Jun 2026 19:04:18 +0000") == "2026-06-03T19:04:18+00:00"
        assert normalize_date("15 Dec 2025 10:00:00 +0000").startswith("2025-12-15")

    def test_le_jour_reste_devant_le_mois(self):
        assert normalize_date("03/02/2026").startswith("2026-02-03")
