"""Sorties publiées : flux RSS, OPML, tableau de bord."""

from __future__ import annotations

import re
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


class TestFluxDeterministe:
    """Un contenu inchangé doit produire un fichier identique."""

    ARTICLES = [
        Item("S", "Récent", "https://exemple.fr/a", published="2026-08-25T10:00:00+00:00"),
        Item("S", "Ancien", "https://exemple.fr/b", published="2026-07-15T10:00:00+00:00"),
    ]

    def test_deux_ecritures_identiques_donnent_le_meme_fichier(self, tmp_path):
        premier, second = tmp_path / "1.xml", tmp_path / "2.xml"
        write_feed(self.ARTICLES, "T", "D", premier, HOME, HOME + "f.xml")
        write_feed(self.ARTICLES, "T", "D", second, HOME, HOME + "f.xml")
        assert premier.read_bytes() == second.read_bytes()

    def test_last_build_date_suit_le_plus_recent_article(self, tmp_path):
        sortie = tmp_path / "flux.xml"
        write_feed(self.ARTICLES, "T", "D", sortie, HOME)
        construit = ET.parse(sortie).findtext(".//channel/lastBuildDate")
        assert parsedate_to_datetime(construit).date().isoformat() == "2026-08-25"

    def test_un_flux_vide_reste_ecrit(self, tmp_path):
        sortie = tmp_path / "flux.xml"
        write_feed([], "T", "D", sortie, HOME)
        assert ET.parse(sortie).findtext(".//channel/title") == "T"


def source_status(nom, court, theme, feed, statut="ok"):
    return {"site": nom, "short_name": court, "theme": theme, "url": f"https://{feed}",
            "status": statut, "method": "flux officiel", "items": 5, "feed": feed}


TROIS_SOURCES = [
    source_status("Enfance & Jeunesse Infos - Veille juridique", "Enfance & Jeunesse Infos",
                  "Enfance & Éducation", "eji.xml"),
    source_status("CNSA - Actualités", "CNSA", "Santé, social & séniors", "cnsa.xml"),
    source_status("IGAS", "IGAS", "Santé, social & séniors", "igas.xml"),
]


def creer_flux(tmp_path, statuses):
    for st in statuses:
        (tmp_path / st["feed"]).write_text("<rss/>", encoding="utf-8")


class TestGroupementParDomaine:
    def test_le_tableau_porte_un_intertitre_par_domaine(self, tmp_path):
        creer_flux(tmp_path, TROIS_SOURCES)
        write_dashboard({**PAYLOAD, "sites": TROIS_SOURCES}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert page.count('<tr class="theme" id="domaine-') == 2
        assert "Enfance &amp; Éducation" in page and "Santé, social &amp; séniors" in page

    def test_le_nom_court_est_affiche_le_nom_complet_au_survol(self, tmp_path):
        creer_flux(tmp_path, TROIS_SOURCES)
        write_dashboard({**PAYLOAD, "sites": TROIS_SOURCES}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert ">Enfance &amp; Jeunesse Infos<" in page
        assert 'title="Enfance &amp; Jeunesse Infos - Veille juridique"' in page

    def test_un_domaine_n_apparait_qu_une_fois(self, tmp_path):
        creer_flux(tmp_path, TROIS_SOURCES)
        write_dashboard({**PAYLOAD, "sites": TROIS_SOURCES}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert page.count('<th colspan="6">Santé, social &amp; séniors</th>') == 1

    def test_l_opml_cree_un_dossier_par_domaine(self, tmp_path):
        creer_flux(tmp_path, TROIS_SOURCES)
        write_opml(TROIS_SOURCES, HOME, public_dir=tmp_path)
        arbre = ET.parse(tmp_path / "feeds.opml")
        dossiers = arbre.findall(".//body/outline")
        assert [d.get("text") for d in dossiers] == ["Enfance & Éducation", "Santé, social & séniors"]
        assert len(dossiers[1].findall("outline")) == 2

    def test_l_opml_emploie_les_noms_courts(self, tmp_path):
        creer_flux(tmp_path, TROIS_SOURCES)
        write_opml(TROIS_SOURCES, HOME, public_dir=tmp_path)
        contenu = (tmp_path / "feeds.opml").read_text(encoding="utf-8")
        assert 'text="CNSA"' in contenu
        assert "CNSA - Actualités" not in contenu

    def test_l_opml_reste_valide_si_un_flux_manque(self, tmp_path):
        """Le dossier d'un domaine dont aucun flux n'existe ne doit pas rester ouvert."""
        (tmp_path / "eji.xml").write_text("<rss/>", encoding="utf-8")
        write_opml(TROIS_SOURCES, HOME, public_dir=tmp_path)
        arbre = ET.parse(tmp_path / "feeds.opml")
        assert len(arbre.findall(".//outline[@type='rss']")) == 1


class TestIndicateurDeFraicheur:
    """La page est statique : seul le navigateur peut voir qu'elle a vieilli."""

    def _page(self, tmp_path):
        write_dashboard({**PAYLOAD, "sites": []}, "T", public_dir=tmp_path)
        return (tmp_path / "index.html").read_text(encoding="utf-8")

    def test_la_date_de_generation_est_lisible_par_machine(self, tmp_path):
        page = self._page(tmp_path)
        assert f'<time id="generation" datetime="{PAYLOAD["generated_at"]}"' in page

    def test_le_bandeau_d_alerte_est_masque_par_defaut(self, tmp_path):
        """Sans JavaScript, aucune alerte ne doit s'afficher à tort."""
        page = self._page(tmp_path)
        assert '<div id="alerte" hidden class="stale">' in page

    def test_le_seuil_d_alerte_est_celui_du_module(self, tmp_path):
        from veille.output import STALE_AFTER_HOURS
        assert f"heures >= {STALE_AFTER_HOURS}" in self._page(tmp_path)

    def test_le_seuil_laisse_passer_la_dispersion_du_planificateur(self):
        """La veille tourne toutes les 3 h, avec un décalage courant de plusieurs heures."""
        from veille.output import STALE_AFTER_HOURS
        assert STALE_AFTER_HOURS >= 6

    def test_la_page_reste_lisible_sans_javascript(self, tmp_path):
        page = self._page(tmp_path)
        assert PAYLOAD["generated_at"] in page.split("<script>")[0]


class TestBoutonProposerUneSource:
    def test_le_tableau_de_bord_mene_au_formulaire(self, tmp_path):
        from veille.output import PROPOSE_SOURCE_URL
        write_dashboard({**PAYLOAD, "sites": []}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert f'href="{PROPOSE_SOURCE_URL}">Proposer une source</a>' in page
        assert "template=nouvelle-source.yml" in PROPOSE_SOURCE_URL

    def test_le_tableau_de_bord_mene_aussi_au_formulaire_de_domaine(self, tmp_path):
        from veille.output import PROPOSE_THEME_URL
        write_dashboard({**PAYLOAD, "sites": []}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert f'href="{PROPOSE_THEME_URL}">Proposer un domaine</a>' in page
        assert "template=nouveau-domaine.yml" in PROPOSE_THEME_URL


class TestSommaireDesDomaines:
    """Une colonne listant les domaines, chaque entrée menant à sa rubrique."""

    SOURCES = [
        source_status("Observatoire", "Observatoire", "Culture", "obs.xml"),
        source_status("EJI", "Enfance & Jeunesse Infos", "Enfance & Éducation", "eji.xml"),
        source_status("Pros", "Pros de la petite enfance", "Enfance & Éducation", "pros.xml"),
        source_status("ANAP", "ANAP", "Santé, social & séniors", "anap.xml", "error"),
        source_status("CNSA", "CNSA", "Santé, social & séniors", "cnsa.xml"),
    ]

    def _page(self, tmp_path, sources=None):
        sources = self.SOURCES if sources is None else sources
        creer_flux(tmp_path, sources)
        write_dashboard({**PAYLOAD, "sites": sources}, "T", public_dir=tmp_path)
        return (tmp_path / "index.html").read_text(encoding="utf-8")

    def test_l_ancre_est_lisible_et_sans_accent(self):
        from veille.output import theme_anchor
        assert theme_anchor("Santé, social & séniors") == "domaine-sante-social-seniors"
        assert theme_anchor("Enfance & Éducation") == "domaine-enfance-education"

    def test_chaque_domaine_a_son_entree_et_sa_cible(self, tmp_path):
        import re
        page = self._page(tmp_path)
        liens = re.findall(r'nav class="domaines".*?</nav>', page, re.S)[0]
        cibles = re.findall(r'href="#([^"]+)"', liens)
        assert cibles == ["domaine-culture", "domaine-enfance-education", "domaine-sante-social-seniors"]
        for cible in cibles:
            assert f'<tr class="theme" id="{cible}">' in page

    def test_compte_les_sources_par_domaine(self, tmp_path):
        page = self._page(tmp_path)
        assert 'Enfance &amp; Éducation</a> <span class="compte">2</span>' in page
        assert 'Culture</a> <span class="compte">1</span>' in page

    def test_signale_un_domaine_avec_une_source_en_erreur(self, tmp_path):
        import re
        page = self._page(tmp_path)
        nav = re.findall(r'nav class="domaines".*?</nav>', page, re.S)[0]
        entrees = re.findall(r"<li>.*?</li>", nav)
        assert "⚠" in entrees[2] and "1 source(s) en erreur" in entrees[2]
        assert "⚠" not in entrees[0]

    def test_le_sommaire_precede_le_tableau(self, tmp_path):
        page = self._page(tmp_path)
        assert page.index('nav class="domaines"') < page.index("<table>")

    def test_pas_de_sommaire_sans_source(self, tmp_path):
        page = self._page(tmp_path, sources=[])
        assert 'nav class="domaines"' not in page

    def test_les_sources_sans_domaine_ne_creent_pas_d_entree(self, tmp_path):
        sans_domaine = dict(source_status("X", "X", "", "x.xml"))
        page = self._page(tmp_path, sources=[sans_domaine])
        assert 'nav class="domaines"' not in page


class TestColonneActivite:
    """L'adresse du flux propre au site, en clair, pour la copier d'un geste."""

    LOCALTIS = "https://www.banquedesterritoires.fr/flux/publics-fragiles/localtis.xml"

    def _page(self, tmp_path, *sites):
        creer_flux(tmp_path, sites)
        write_dashboard({**PAYLOAD, "sites": list(sites)}, "T", public_dir=tmp_path)
        return (tmp_path / "index.html").read_text(encoding="utf-8")

    def test_l_ordre_des_colonnes(self, tmp_path):
        """« Flux » = adresse publiée par le site ; « Activité » = flux de la veille ; le détail en dernier."""
        page = self._page(tmp_path, source_status("A", "A", "Culture", "a.xml"))
        assert ("<th>Source</th><th>État</th><th>Articles</th><th>Flux</th>"
                "<th>Activité</th><th>Méthode / détail</th>") in page

    def test_les_cellules_suivent_l_ordre_des_en_tetes(self, tmp_path):
        site = {**source_status("L", "L", "Culture", "l.xml"), "source_feed": self.LOCALTIS}
        page = self._page(tmp_path, site)
        ligne = next(tr for tr in page.split("<tr>") if 'class="activite"' in tr)
        assert ligne.index('class="activite"') < ligne.index('href="l.xml"') < ligne.index("flux officiel")

    def test_affiche_l_adresse_du_flux_natif_en_clair(self, tmp_path):
        site = {**source_status("Localtis - Publics fragiles", "Localtis — Publics fragiles",
                                "Santé, social & séniors", "lpf.xml"), "source_feed": self.LOCALTIS}
        page = self._page(tmp_path, site)
        assert f'<a class="url" href="{self.LOCALTIS}">{self.LOCALTIS}</a>' in page

    def test_offre_un_bouton_copier_portant_l_adresse(self, tmp_path):
        site = {**source_status("L", "L", "Culture", "l.xml"), "source_feed": self.LOCALTIS}
        page = self._page(tmp_path, site)
        assert f'<button type="button" class="copier" data-url="{self.LOCALTIS}"' in page
        assert "navigator.clipboard" in page

    def test_montre_aussi_un_flux_detecte(self, tmp_path):
        site = {**source_status("P", "P", "Culture", "p.xml"), "method": "flux détecté",
                "source_feed": "https://www.exemple.fr/actualites/feed/"}
        assert "https://www.exemple.fr/actualites/feed/</a>" in self._page(tmp_path, site)

    def test_ne_montre_pas_un_flux_configure_mais_inutilisable(self, tmp_path):
        """Cas C2L : l'adresse configurée sert du HTML, la source vit par repli."""
        site = {**source_status("C2L", "C2L", "Restauration", "c2l.xml"), "method": "repli : html_selectors",
                "source_feed": "https://www.c2lsolutions.fr/category/actus/feed/"}
        page = self._page(tmp_path, site)
        assert "c2lsolutions.fr/category/actus/feed/" not in page
        assert 'class="absent">pas de flux publié</span>' in page

    def test_mention_lisible_pour_une_source_lue_sur_sa_page(self, tmp_path):
        site = {**source_status("SNRC", "SNRC", "Restauration", "snrc.xml"), "method": "html_selectors",
                "source_feed": ""}
        page = self._page(tmp_path, site)
        assert "pas de flux publié" in page
        assert "colonne Activité" in page, "l'infobulle renvoie vers le flux de la veille"

    def test_signale_un_flux_general_filtre_sur_une_categorie(self, tmp_path):
        site = {**source_status("C2L", "C2L", "Restauration", "c2l.xml"),
                "source_feed": "https://c2lsolutions.fr/feed/?post_type=post",
                "feed_categories": ["La restauration collective"]}
        page = self._page(tmp_path, site)
        assert "https://c2lsolutions.fr/feed/?post_type=post</a>" in page
        assert 'class="filtre"' in page and "filtré : La restauration collective" in page

    def test_les_intertitres_enjambent_toutes_les_colonnes(self, tmp_path):
        page = self._page(tmp_path, source_status("A", "A", "Culture", "a.xml"))
        assert page.count("<th>") == 6, "six en-têtes de colonnes"
        assert '<th colspan="6">Culture</th>' in page, "l'intertitre de domaine enjambe les six colonnes"


class TestColonneDetailCompacte:
    """La méthode et un résumé lisible ; le message brut repliable derrière."""

    ANAP = ("HTTPSConnectionPool(host='www.anap.fr', port=443): Max retries exceeded with url: "
            "/s/sitemap-topicarticle-1.xml (Caused by SSLError(SSLCertVerificationError(1, "
            "'[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer "
            "certificate (_ssl.c:1010)')))")

    def test_resume_les_erreurs_courantes(self):
        from veille.output import summarize_error
        assert summarize_error(self.ANAP) == "certificat TLS du site incomplet"
        assert summarize_error("https://x/feed/ ne sert pas un flux (contenu text/html)") == (
            "le flux annoncé renvoie une page, pas un flux")
        assert summarize_error("Aucun article détecté sur la page") == "aucun article détecté"
        assert summarize_error("404 Client Error: Not Found for url: https://x") == "page introuvable (404)"
        assert summarize_error("HTTPSConnectionPool: Read timed out. (read timeout=30)") == "délai de réponse dépassé"

    def test_tronque_un_message_inconnu(self):
        from veille.output import summarize_error
        court = summarize_error("x" * 200)
        assert len(court) <= 70 and court.endswith("…")
        assert summarize_error("petit souci") == "petit souci"

    def test_une_source_ok_montre_seulement_la_methode(self, tmp_path):
        creer_flux(tmp_path, [source_status("A", "A", "Culture", "a.xml")])
        write_dashboard({**PAYLOAD, "sites": [source_status("A", "A", "Culture", "a.xml")]}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert '<td class="detail">flux officiel</td>' in page
        assert "<details>" not in page

    def test_une_erreur_est_resumee_et_repliable(self, tmp_path):
        site = {**source_status("ANAP", "ANAP", "Santé, social & séniors", "anap.xml", "error"),
                "method": "historique conservé", "error": self.ANAP}
        creer_flux(tmp_path, [site])
        write_dashboard({**PAYLOAD, "sites": [site]}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert "<summary>historique conservé — certificat TLS du site incomplet</summary>" in page
        assert "CERTIFICATE_VERIFY_FAILED" in page, "le message brut reste consultable"
        assert page.index("<summary>") < page.index("CERTIFICATE_VERIFY_FAILED")

    def test_l_adresse_du_flux_ne_se_coupe_plus(self, tmp_path):
        write_dashboard({**PAYLOAD, "sites": []}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert "td.activite{white-space:nowrap}" in page
        assert "word-break:break-all}" not in page.split("td.detail .brut")[0].split("a.url")[1]


class TestLiensDeGestion:
    def test_les_cinq_formulaires_sont_accessibles(self, tmp_path):
        from veille.output import (
            PROPOSE_SOURCE_URL, PROPOSE_THEME_URL, REMOVE_SOURCE_URL, REMOVE_THEME_URL, RENAME_THEME_URL,
        )
        write_dashboard({**PAYLOAD, "sites": []}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert f'href="{REMOVE_SOURCE_URL}">Supprimer une source</a>' in page
        assert f'href="{RENAME_THEME_URL}">Renommer un domaine</a>' in page
        assert f'href="{REMOVE_THEME_URL}">Supprimer un domaine</a>' in page
        assert "template=supprimer-source.yml" in REMOVE_SOURCE_URL
        assert "template=renommer-domaine.yml" in RENAME_THEME_URL
        assert "template=supprimer-domaine.yml" in REMOVE_THEME_URL
        assert (page.index(PROPOSE_SOURCE_URL) < page.index(REMOVE_SOURCE_URL) < page.index(PROPOSE_THEME_URL)
                < page.index(RENAME_THEME_URL) < page.index(REMOVE_THEME_URL))


class TestSurveillance:
    """Une source OK peut être « à surveiller » : ⚠ orange, détail en clair, compteur."""

    AVERTISSEMENT = "rien de neuf depuis 203 jours (seuil : 60)"

    def _sources(self):
        return [
            {**source_status("SNRC", "SNRC", "Restauration", "snrc.xml"), "warnings": [self.AVERTISSEMENT]},
            {**source_status("C2L", "C2L", "Restauration", "c2l.xml"), "warnings": []},
            {**source_status("ANAP", "ANAP", "Santé, social & séniors", "anap.xml", "error"),
             "error": "boom", "warnings": ["sans objet pour une erreur"]},
            source_status("CNSA", "CNSA", "Santé, social & séniors", "cnsa.xml"),
        ]

    def _page(self, tmp_path, sources=None):
        sources = self._sources() if sources is None else sources
        creer_flux(tmp_path, sources)
        write_dashboard({**PAYLOAD, "sites_warning": 1, "sites": sources}, "T", public_dir=tmp_path)
        return (tmp_path / "index.html").read_text(encoding="utf-8")

    def _ligne(self, page, nom):
        return re.search(rf'<tr><td><span title="{nom}">.*?</tr>', page, re.S).group(0)

    def test_un_avertissement_marque_l_etat_sans_le_changer(self, tmp_path):
        ligne = self._ligne(self._page(tmp_path), "SNRC")
        assert ("<span class='ok'>OK</span> "
                f'<span class="warn" title="À surveiller : {self.AVERTISSEMENT}">⚠</span>') in ligne
        assert f'<span class="avert">⚠ {self.AVERTISSEMENT}</span>' in ligne

    def test_une_source_sans_avertissement_reste_intacte(self, tmp_path):
        assert "⚠" not in self._ligne(self._page(tmp_path), "C2L")

    def test_une_source_en_erreur_n_affiche_pas_d_avertissement(self, tmp_path):
        ligne = self._ligne(self._page(tmp_path), "ANAP")
        assert "sans objet pour une erreur" not in ligne
        assert ">ERREUR<" in ligne

    def test_le_sommaire_signale_un_domaine_a_surveiller_l_erreur_primant(self, tmp_path):
        page = self._page(tmp_path)
        nav = re.findall(r'nav class="domaines".*?</nav>', page, re.S)[0]
        entrees = re.findall(r"<li>.*?</li>", nav)
        assert '<span class="warn" title="1 source(s) à surveiller">⚠</span>' in entrees[0]
        assert '<span class="error" title="1 source(s) en erreur">⚠</span>' in entrees[1]
        assert "à surveiller" not in entrees[1]

    def test_le_compteur_a_surveiller_figure_parmi_les_cartes(self, tmp_path):
        page = self._page(tmp_path)
        assert "<strong>1</strong><br>à surveiller" in page
        assert page.index("opérationnelles") < page.index("à surveiller") < page.index("en erreur")

    def test_un_etat_json_sans_surveillance_reste_lisible(self, tmp_path):
        """Les status.json antérieurs n'ont ni compteur ni avertissements."""
        sources = [source_status("CNSA", "CNSA", "Santé, social & séniors", "cnsa.xml")]
        creer_flux(tmp_path, sources)
        write_dashboard({**PAYLOAD, "sites": sources}, "T", public_dir=tmp_path)
        page = (tmp_path / "index.html").read_text(encoding="utf-8")
        assert "<strong>0</strong><br>à surveiller" in page
        assert "⚠" not in re.search(r"<tbody>.*</tbody>", page, re.S).group(0)

    def test_les_avertissements_sont_echappes(self, tmp_path):
        sources = [{**source_status("X", "X", "Culture", "x.xml"), "warnings": ['titre "douteux" <b>']}]
        page = self._page(tmp_path, sources)
        assert 'title="À surveiller : titre &quot;douteux&quot; &lt;b&gt;"' in page
        assert '<span class="avert">⚠ titre &quot;douteux&quot; &lt;b&gt;</span>' in page
