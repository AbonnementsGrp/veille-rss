"""Sorties publiées : flux RSS, OPML, tableau de bord."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from veille.models import Item
from veille.output import write_dashboard, write_feed, write_opml

HOME = "https://exemple.fr/"


def items_of(path):
    return ET.parse(path).findall(".//item")


def dates_of(path):
    return [parsedate_to_datetime(i.findtext("pubDate")) for i in items_of(path)]


class TestWriteFeed:
    def test_ecrit_un_flux_rss_lisible(self, tmp_path):
        sortie = tmp_path / "flux.xml"
        write_feed(
            [Item("Ma source", "Un article", "https://exemple.fr/a", "Un résumé", "2026-08-25T10:00:00+00:00")],
            "Titre du flux", "Description du flux", sortie, HOME, HOME + "flux.xml",
        )
        arbre = ET.parse(sortie)
        assert arbre.findtext(".//channel/title") == "Titre du flux"
        assert arbre.findtext(".//item/title") == "Un article"
        assert arbre.findtext(".//item/link") == "https://exemple.fr/a"

    def test_trie_du_plus_recent_au_plus_ancien(self, tmp_path):
        """Régression : les flux publiés n'étaient pas triés chronologiquement.

        Le mélange ISO / RFC-822 issu de l'historique remontait de vieux
        articles en tête de veille.xml.
        """
        sortie = tmp_path / "flux.xml"
        write_feed([
            Item("S", "Juillet", "https://exemple.fr/3", published="2026-07-15T10:00:00+00:00"),
            Item("S", "Ancien au format RFC-822", "https://exemple.fr/4", published="Wed, 03 Jun 2026 19:04:18 +0000"),
            Item("S", "Août", "https://exemple.fr/1", published="2026-08-25T10:00:00+00:00"),
            Item("S", "Sans date", "https://exemple.fr/5"),
            Item("S", "Août, plus tôt", "https://exemple.fr/2", published="2026-08-20T10:00:00+00:00"),
        ], "T", "D", sortie, HOME)
        titres = [i.findtext("title") for i in items_of(sortie)]
        assert titres == ["Août", "Août, plus tôt", "Juillet", "Ancien au format RFC-822", "Sans date"]

    def test_les_dates_publiees_sont_decroissantes(self, tmp_path):
        sortie = tmp_path / "flux.xml"
        write_feed([
            Item("S", "A", "https://exemple.fr/a", published="2026-01-05T00:00:00+00:00"),
            Item("S", "B", "https://exemple.fr/b", published="Fri, 10 Jul 2026 08:42:08 +0000"),
            Item("S", "C", "https://exemple.fr/c", published="2026-03-11T00:00:00+00:00"),
        ], "T", "D", sortie, HOME)
        dates = dates_of(sortie)
        assert dates == sorted(dates, reverse=True)

    def test_se_replie_sur_la_date_de_decouverte(self, tmp_path):
        sortie = tmp_path / "flux.xml"
        write_feed(
            [Item("S", "A", "https://exemple.fr/a", first_seen="2026-08-25T10:00:00+00:00")],
            "T", "D", sortie, HOME,
        )
        assert dates_of(sortie)[0].day == 25

    def test_remplace_un_resume_absent(self, tmp_path):
        sortie = tmp_path / "flux.xml"
        write_feed([Item("Ma source", "A", "https://exemple.fr/a")], "T", "D", sortie, HOME)
        assert ET.parse(sortie).findtext(".//item/description") == "Source : Ma source"

    def test_cree_le_dossier_de_sortie(self, tmp_path):
        sortie = tmp_path / "public" / "flux.xml"
        write_feed([Item("S", "A", "https://exemple.fr/a")], "T", "D", sortie, HOME)
        assert sortie.exists()


def status(site, feed, statut="ok", **kw):
    return {"site": site, "url": f"https://{site}.fr/actu", "status": statut, "method": "flux officiel",
            "items": 3, "feed": feed, **kw}


class TestWriteOpml:
    def test_liste_les_flux_existants(self, tmp_path):
        (tmp_path / "a.xml").write_text("<rss/>", encoding="utf-8")
        write_opml([status("source-a", "a.xml")], HOME, public_dir=tmp_path)
        contenu = (tmp_path / "feeds.opml").read_text(encoding="utf-8")
        assert 'xmlUrl="https://exemple.fr/a.xml"' in contenu

    def test_n_annonce_pas_un_flux_absent(self, tmp_path):
        """Un flux listé mais introuvable (404) casse l'import côté lecteur."""
        write_opml([status("anap", "anap.xml", "error", error="Aucun article détecté")], HOME, public_dir=tmp_path)
        assert "anap.xml" not in (tmp_path / "feeds.opml").read_text(encoding="utf-8")

    def test_reste_un_opml_valide_sans_aucune_source(self, tmp_path):
        write_opml([], HOME, public_dir=tmp_path)
        assert ET.parse(tmp_path / "feeds.opml").getroot().tag == "opml"


PAYLOAD = {
    "generated_at": "2026-08-27T13:00:00+00:00",
    "sites_total": 2, "sites_ok": 1, "sites_error": 1,
    "new_items": 4, "merged_items": 42,
}


class TestWriteDashboard:
    def test_affiche_l_etat_de_chaque_source(self, tmp_path):
        (tmp_path / "a.xml").write_text("<rss/>", encoding="utf-8")
        payload = {**PAYLOAD, "sites": [
            status("source-a", "a.xml"),
            status("source-b", "b.xml", "error", method="échec", error="Aucun article détecté"),
        ]}
        write_dashboard(payload, "Tableau de bord", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert "source-a" in page and "source-b" in page
        assert ">OK<" in page and ">ERREUR<" in page
        assert "42" in page and "Tableau de bord" in page

    def test_ne_lie_pas_un_flux_absent(self, tmp_path):
        payload = {**PAYLOAD, "sites": [status("anap", "anap.xml", "error", method="échec")]}
        write_dashboard(payload, "T", public_dir=tmp_path)
        assert 'href="anap.xml"' not in (tmp_path / "index.html").read_text(encoding="utf-8")

    def test_echappe_le_message_d_erreur_une_seule_fois(self, tmp_path):
        """Le double échappement affichait "&lt;unknown&gt;" à l'écran."""
        payload = {**PAYLOAD, "sites": [
            status("c2l", "c2l.xml", "error", method="échec", error="Flux RSS invalide : <unknown>:12:27"),
        ]}
        write_dashboard(payload, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert "&lt;unknown&gt;" in page
        assert "&amp;lt;unknown" not in page
