"""Enquête sur une URL en vue d'en faire une source : verdict, proposition, écriture."""

from __future__ import annotations

import yaml
import pytest

from veille.models import Item
from veille.onboarding import (
    VERDICT_A_VERIFIER,
    VERDICT_MANUEL,
    VERDICT_OK,
    Proposal,
    append_site,
    investigate,
    juger,
    render_block,
    site_name_from_html,
)

CFG = {
    "settings": {"themes": ["Enfance & Éducation", "Culture"]},
    "sites": [
        {"name": "CNSA - Actualités", "url": "https://www.cnsa.fr/actualites",
         "official_feed": "https://www.cnsa.fr/flux-rss.xml/article", "output": "cnsa.xml"},
    ],
}


class Reponse:
    def __init__(self, contenu: bytes, url: str, content_type: str):
        self.content = contenu
        self.text = contenu.decode("utf-8", "replace")
        self.url = url
        self.ok = True
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        return None


class SiteFactice:
    """Un site : une page HTML, et éventuellement un flux à une adresse donnée."""

    def __init__(self, page: str, flux: bytes | None = None, flux_url: str = ""):
        self.page = page
        self.flux = flux
        self.flux_url = flux_url
        self.urls: list[str] = []

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        if self.flux is not None and url.rstrip("/") == self.flux_url.rstrip("/"):
            return Reponse(self.flux, url, "application/rss+xml")
        return Reponse(self.page.encode("utf-8"), url, "text/html; charset=UTF-8")


PAGE_AVEC_TITRE = "<html><head><title>Actualités - Mon Organisme</title></head><body>{corps}</body></html>"


class TestSiteNameFromHtml:
    def test_prefere_og_site_name(self):
        html = '<html><head><meta property="og:site_name" content="Mon Organisme"><title>Actus | x</title></head></html>'
        assert site_name_from_html(html) == "Mon Organisme"

    def test_ecarte_le_segment_rubrique_du_title(self):
        assert site_name_from_html(PAGE_AVEC_TITRE.format(corps="")) == "Mon Organisme"

    def test_garde_un_title_simple(self):
        assert site_name_from_html("<html><head><title>Mon Organisme</title></head></html>") == "Mon Organisme"

    def test_rend_vide_sans_titre(self):
        assert site_name_from_html("<html><body></body></html>") == ""


class TestJuger:
    def _items(self, n, dates=True):
        return [Item("S", f"Titre {k}", f"https://exemple.fr/{k}",
                     published="2026-08-25T10:00:00+00:00" if dates else "") for k in range(n)]

    def test_ok_quand_tout_va_bien(self):
        verdict, reserves = juger(self._items(10), "flux détecté")
        assert verdict == VERDICT_OK and reserves == []

    def test_manuel_sans_aucun_article(self):
        verdict, reserves = juger([], "generic_links")
        assert verdict == VERDICT_MANUEL and "JavaScript" in reserves[0]

    def test_a_verifier_si_trop_peu_d_articles(self):
        assert juger(self._items(2), "html_selectors")[0] == VERDICT_A_VERIFIER

    def test_a_verifier_si_les_dates_manquent(self):
        verdict, reserves = juger(self._items(10, dates=False), "html_selectors")
        assert verdict == VERDICT_A_VERIFIER and any("sans date" in r for r in reserves)

    def test_a_verifier_si_la_methode_est_fragile(self):
        verdict, reserves = juger(self._items(10), "generic_links")
        assert verdict == VERDICT_A_VERIFIER and any("notation des liens" in r for r in reserves)


class TestInvestigate:
    def test_trouve_le_flux_et_propose_une_configuration_complete(self, fixture_bytes):
        site = SiteFactice(PAGE_AVEC_TITRE.format(corps=""), fixture_bytes("wordpress_feed.xml"),
                           "https://exemple.fr/actualites/feed/")
        p = investigate(site, "https://exemple.fr/actualites/", theme="Culture", cfg=CFG)
        assert p.method == "flux détecté"
        assert p.official_feed == "https://exemple.fr/actualites/feed/"
        assert p.name == "Mon Organisme"
        assert p.output == "mon-organisme.xml"
        assert p.verdict == VERDICT_A_VERIFIER  # le flux de test n'a que deux articles
        assert p.to_site() == {
            "name": "Mon Organisme", "theme": "Culture", "url": "https://exemple.fr/actualites/",
            "official_feed": "https://exemple.fr/actualites/feed/", "output": "mon-organisme.xml",
        }

    def test_se_replie_sur_la_page_sans_flux(self, fixture_text):
        page = fixture_text("page_selectors.html")
        p = investigate(SiteFactice(page), "https://exemple.fr/actualites/", cfg=CFG)
        assert p.method == "html_selectors"
        assert p.official_feed == ""
        assert len(p.items) == 2

    def test_verdict_manuel_sur_une_page_vide(self):
        p = investigate(SiteFactice("<html><body><p>Rien ici</p></body></html>"),
                        "https://exemple.fr/vide/", cfg=CFG)
        assert p.verdict == VERDICT_MANUEL

    def test_signale_une_adresse_deja_suivie(self, fixture_bytes):
        site = SiteFactice("<html></html>", fixture_bytes("wordpress_feed.xml"), "https://www.cnsa.fr/actualites/feed/")
        p = investigate(site, "https://www.cnsa.fr/actualites/", cfg=CFG)
        assert any("déjà suivie" in w and "CNSA" in w for w in p.warnings)
        assert p.verdict != VERDICT_OK, "un doublon ne doit jamais être annoncé comme prêt"

    def test_signale_un_domaine_inconnu(self):
        p = investigate(SiteFactice("<html></html>"), "https://exemple.fr/", theme="Sport", cfg=CFG)
        assert any("Autres" in w for w in p.warnings)

    def test_le_nom_fourni_prime_et_baptise_les_articles(self, fixture_text):
        page = fixture_text("page_selectors.html")
        p = investigate(SiteFactice(page), "https://exemple.fr/actualites/", name="Mon Nom", cfg=CFG)
        assert p.name == "Mon Nom" and all(i.source == "Mon Nom" for i in p.items)

    def test_evite_une_collision_de_fichier_de_sortie(self):
        p = investigate(SiteFactice("<html></html>"), "https://autre.fr/", name="CNSA", cfg=CFG)
        assert p.output == "cnsa-2.xml"


class NavigateurFactice:
    """Tient lieu de BrowserSession : rend une page donnée, ou échoue."""

    def __init__(self, page: str = "", panne: str = ""):
        self.page = page
        self.panne = panne
        self.urls: list[str] = []

    def get(self, url, timeout=None, allow_redirects=False):
        self.urls.append(url)
        if self.panne:
            raise RuntimeError(self.panne)
        return Reponse(self.page.encode("utf-8"), url, "text/html; charset=UTF-8")


class TestInvestigateAvecNavigateur:
    """Une page vide pour la session HTTP est rendue en JavaScript avant de conclure."""

    COQUILLE = "<html><head><title>Site de l'Anap</title></head><body><div id='app'></div></body></html>"

    def test_propose_le_rendu_quand_seul_le_navigateur_voit_des_articles(self, fixture_text):
        navigateur = NavigateurFactice(fixture_text("page_selectors.html"))
        p = investigate(SiteFactice(self.COQUILLE), "https://exemple.fr/s/actualites", theme="Culture",
                        cfg=CFG, browser=navigateur)
        assert p.render is True
        assert p.method == "navigateur : html_selectors"
        assert len(p.items) == 2
        assert navigateur.urls == ["https://exemple.fr/s/actualites"]
        assert p.verdict == VERDICT_A_VERIFIER, "un site rendu en JavaScript mérite un regard humain"
        assert any("navigateur" in w for w in p.warnings)
        assert p.to_site()["mode"] == "page"
        assert p.to_site()["render"] is True

    def test_le_navigateur_n_est_pas_sollicite_quand_la_page_suffit(self, fixture_text):
        navigateur = NavigateurFactice("<html></html>")
        p = investigate(SiteFactice(fixture_text("page_selectors.html")), "https://exemple.fr/actualites/",
                        cfg=CFG, browser=navigateur)
        assert p.render is False
        assert navigateur.urls == []
        assert "render" not in p.to_site()

    def test_une_page_vide_meme_rendue_reste_manuelle(self):
        p = investigate(SiteFactice(self.COQUILLE), "https://exemple.fr/vide/", cfg=CFG,
                        browser=NavigateurFactice(self.COQUILLE))
        assert p.verdict == VERDICT_MANUEL
        assert p.render is False

    def test_un_navigateur_en_panne_est_signale_sans_faire_echouer_l_enquete(self):
        p = investigate(SiteFactice(self.COQUILLE), "https://exemple.fr/vide/", cfg=CFG,
                        browser=NavigateurFactice(panne="navigateur indisponible : installer Playwright"))
        assert p.verdict == VERDICT_MANUEL
        assert any("rendu par navigateur impossible" in w for w in p.warnings)


class TestRenderBlock:
    def test_ecrit_dans_le_style_du_fichier(self):
        bloc = render_block({"name": "Mon Organisme", "theme": "Culture", "url": "https://exemple.fr/"})
        assert bloc == '  - name: "Mon Organisme"\n    theme: "Culture"\n    url: "https://exemple.fr/"\n'

    def test_le_bloc_est_du_yaml_valide(self):
        bloc = render_block({"name": 'Nom avec "guillemets"', "url": "https://exemple.fr/"})
        assert yaml.safe_load("sites:\n" + bloc)["sites"][0]["url"] == "https://exemple.fr/"

    def test_un_booleen_s_ecrit_sans_guillemets(self):
        bloc = render_block({"name": "Site JS", "url": "https://exemple.fr/", "mode": "page", "render": True})
        assert bloc.endswith('    mode: "page"\n    render: true\n')
        assert yaml.safe_load("sites:\n" + bloc)["sites"][0]["render"] is True


class TestAppendSite:
    CONFIG = 'settings:\n  themes: ["Culture"]\n\nsites:\n  - name: "A"\n    url: "https://a.fr/"\n    output: "a.xml"\n'

    def _fichier(self, tmp_path):
        p = tmp_path / "sites.yml"
        p.write_text(self.CONFIG, encoding="utf-8")
        return p

    def test_ajoute_en_fin_sans_toucher_au_reste(self, tmp_path):
        p = self._fichier(tmp_path)
        append_site({"name": "B", "url": "https://b.fr/", "output": "b.xml"}, p)
        texte = p.read_text(encoding="utf-8")
        assert texte.startswith(self.CONFIG.rstrip("\n"))
        assert [s["name"] for s in yaml.safe_load(texte)["sites"]] == ["A", "B"]

    def test_refuse_un_nom_en_double(self, tmp_path):
        with pytest.raises(ValueError, match="existe déjà"):
            append_site({"name": "A", "url": "https://x.fr/", "output": "x.xml"}, self._fichier(tmp_path))

    def test_refuse_un_fichier_de_sortie_en_double(self, tmp_path):
        with pytest.raises(ValueError, match="déjà utilisé"):
            append_site({"name": "C", "url": "https://c.fr/", "output": "a.xml"}, self._fichier(tmp_path))

    def test_preserve_les_commentaires(self, tmp_path):
        p = tmp_path / "sites.yml"
        p.write_text(self.CONFIG.replace('sites:\n', 'sites:\n  # commentaire précieux\n'), encoding="utf-8")
        append_site({"name": "B", "url": "https://b.fr/", "output": "b.xml"}, p)
        assert "# commentaire précieux" in p.read_text(encoding="utf-8")
