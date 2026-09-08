"""Navigateur sans tête : réponse rendue, attente, document stable, fermeture.

Playwright est remplacé par un jeu d'objets factices qui journalisent les
appels ; un dernier test, ignoré si Chromium n'est pas installé, rend une vraie
page pour vérifier que le shadow DOM est bien traversé.
"""

from __future__ import annotations

import pytest
import requests

from veille.browser import (
    INSTALL_HINT,
    SETTLE_MS,
    BrowserSession,
    RenderedResponse,
    SiteBrowser,
    needs_render,
)


class FausseReponse:
    def __init__(self, status: int):
        self.status = status


class FaussePage:
    def __init__(self, faux: "FauxPlaywright"):
        self.faux = faux
        self.url = None
        self.fermee = False

    def goto(self, url, timeout, wait_until):
        self.faux.journal.append(("goto", url, wait_until, timeout))
        if self.faux.goto_echoue:
            raise TimeoutError("Timeout 30000ms exceeded")
        self.url = self.faux.url_finale or url
        return None if self.faux.sans_reponse else FausseReponse(self.faux.status)

    def wait_for_selector(self, selecteur, state, timeout):
        self.faux.journal.append(("selector", selecteur, state))

    def wait_for_load_state(self, etat, timeout):
        self.faux.journal.append(("load_state", etat, timeout))

    def wait_for_timeout(self, ms):
        self.faux.journal.append(("sleep", ms))

    def evaluate(self, script):
        self.faux.journal.append(("evaluate",))
        etats = self.faux.etats
        return etats.pop(0) if len(etats) > 1 else etats[0]

    def close(self):
        self.fermee = True
        self.faux.journal.append(("page_close",))


class FauxContexte:
    def __init__(self, faux: "FauxPlaywright"):
        self.faux = faux
        self.routes: list = []
        self.pages: list[FaussePage] = []

    def route(self, motif, handler):
        self.routes.append((motif, handler))

    def new_page(self):
        page = FaussePage(self.faux)
        self.pages.append(page)
        return page

    def close(self):
        self.faux.journal.append(("context_close",))


class FauxNavigateur:
    def __init__(self, faux: "FauxPlaywright"):
        self.faux = faux

    def new_context(self, **options):
        self.faux.options = options
        self.faux.contexte = FauxContexte(self.faux)
        return self.faux.contexte

    def close(self):
        self.faux.journal.append(("browser_close",))


class FauxChromium:
    def __init__(self, faux: "FauxPlaywright"):
        self.faux = faux

    def launch(self, headless):
        if self.faux.lancement_echoue:
            raise RuntimeError("Executable doesn't exist at /chromium")
        self.faux.journal.append(("launch", headless))
        return FauxNavigateur(self.faux)


class FauxPlaywright:
    """Tient lieu de `sync_playwright().start()` et journalise chaque appel."""

    def __init__(self, etats=("<html><body>rendu</body></html>",), status=200, url_finale="",
                 goto_echoue=False, lancement_echoue=False, sans_reponse=False):
        self.etats = list(etats)
        self.status = status
        self.url_finale = url_finale
        self.goto_echoue = goto_echoue
        self.lancement_echoue = lancement_echoue
        self.sans_reponse = sans_reponse
        self.journal: list = []
        self.options: dict = {}
        self.contexte: FauxContexte | None = None
        self.chromium = FauxChromium(self)
        self.arrete = False

    def stop(self):
        self.arrete = True
        self.journal.append(("stop",))


def session_factice(**options) -> tuple[BrowserSession, FauxPlaywright]:
    faux = FauxPlaywright(**options)
    return BrowserSession(user_agent="Test/1.0", playwright_factory=lambda: faux), faux


class TestRenderedResponse:
    def test_ressemble_a_une_reponse_requests(self):
        reponse = RenderedResponse("https://exemple.fr/", 200, "<p>é</p>")
        assert reponse.content == "<p>é</p>".encode("utf-8")
        assert reponse.headers["content-type"].startswith("text/html")
        reponse.raise_for_status()

    def test_signale_une_erreur_http(self):
        with pytest.raises(requests.HTTPError, match="404"):
            RenderedResponse("https://exemple.fr/absent", 404, "").raise_for_status()


class TestBrowserSession:
    def test_le_navigateur_n_est_lance_qu_a_la_premiere_page(self):
        session, faux = session_factice()
        assert faux.journal == []
        session.get("https://exemple.fr/actualites", timeout=12)
        assert faux.journal[0] == ("launch", True)
        assert faux.options["user_agent"] == "Test/1.0"
        assert faux.options["locale"] == "fr-FR"
        assert faux.contexte.routes[0][0] == "**/*"

    def test_livre_le_document_aplati_et_l_adresse_finale(self):
        session, faux = session_factice(url_finale="https://exemple.fr/actualites/", status=200)
        reponse = session.get("https://exemple.fr/actualites", timeout=12)
        assert isinstance(reponse, RenderedResponse)
        assert reponse.text == "<html><body>rendu</body></html>"
        assert reponse.url == "https://exemple.fr/actualites/"
        assert reponse.status_code == 200
        assert session.pages_rendered == 1
        assert faux.contexte.pages[0].fermee, "la page est refermée après lecture"
        assert ("goto", "https://exemple.fr/actualites", "domcontentloaded", 12000) in faux.journal

    def test_une_navigation_sans_reponse_vaut_200(self):
        session, _ = session_factice(sans_reponse=True)
        assert session.get("data:text/html,<p>x</p>").status_code == 200

    def test_attend_le_selecteur_demande_plutot_que_le_calme_du_reseau(self):
        session, faux = session_factice()
        session.get("https://exemple.fr/", timeout=10, wait_for='a[href*="/article/"]')
        assert ("selector", 'a[href*="/article/"]', "attached") in faux.journal
        assert not any(e[0] == "load_state" for e in faux.journal)

    def test_sans_selecteur_attend_le_calme_du_reseau_avec_un_plafond(self):
        session, faux = session_factice()
        session.get("https://exemple.fr/", timeout=60)
        assert ("load_state", "networkidle", 10_000) in faux.journal

    def test_relit_le_document_jusqu_a_ce_qu_il_soit_stable(self):
        session, faux = session_factice(etats=["<p>1</p>", "<p>2</p>", "<p>3</p>", "<p>3</p>"])
        reponse = session.get("https://exemple.fr/", timeout=30)
        assert reponse.text == "<p>3</p>"
        lectures = [e for e in faux.journal if e[0] == "evaluate"]
        assert len(lectures) == 4, "trois états différents, puis une lecture identique à la précédente"
        assert ("sleep", SETTLE_MS) in faux.journal

    def test_un_chargement_interrompu_remonte_une_erreur_lisible_et_referme_la_page(self):
        session, faux = session_factice(goto_echoue=True)
        with pytest.raises(RuntimeError, match="rendu de https://exemple.fr/ interrompu"):
            session.get("https://exemple.fr/", timeout=5)
        assert faux.contexte.pages[0].fermee
        assert session.pages_rendered == 0

    def test_un_navigateur_absent_est_signale_avec_la_marche_a_suivre(self):
        session, faux = session_factice(lancement_echoue=True)
        with pytest.raises(RuntimeError, match="python -m playwright install chromium"):
            session.get("https://exemple.fr/")
        assert faux.arrete, "Playwright est arrêté même quand Chromium manque"
        assert INSTALL_HINT.startswith("navigateur indisponible")

    def test_close_referme_tout_et_reste_idempotent(self):
        session, faux = session_factice()
        session.get("https://exemple.fr/")
        session.close()
        session.close()
        assert faux.journal[-3:] == [("context_close",), ("browser_close",), ("stop",)]

    def test_s_emploie_comme_gestionnaire_de_contexte(self):
        session, faux = session_factice()
        with session as ouverte:
            ouverte.get("https://exemple.fr/")
        assert faux.arrete

    def test_bloque_images_medias_et_polices_mais_laisse_passer_le_reste(self):
        class Route:
            def __init__(self):
                self.sort = ""

            def abort(self):
                self.sort = "abort"

            def continue_(self):
                self.sort = "continue"

        class Requete:
            def __init__(self, genre):
                self.resource_type = genre

        verdicts = {}
        for genre in ("image", "media", "font", "document", "script", "xhr", "fetch", "stylesheet"):
            route = Route()
            BrowserSession._filter_resources(route, Requete(genre))
            verdicts[genre] = route.sort
        assert {g for g, v in verdicts.items() if v == "abort"} == {"image", "media", "font"}


class TestSiteBrowser:
    def test_une_vue_par_source_porte_son_selecteur_d_attente(self):
        session, faux = session_factice()
        vue = session.for_site({"name": "S", "render_wait_for": 'meta[property="og:title"]'})
        assert isinstance(vue, SiteBrowser)
        vue.get("https://exemple.fr/article", timeout=8)
        assert ("selector", 'meta[property="og:title"]', "attached") in faux.journal

    def test_sans_selecteur_configure_la_vue_s_en_remet_au_reseau(self):
        session, faux = session_factice()
        session.for_site({"name": "S"}).get("https://exemple.fr/")
        assert any(e[0] == "load_state" for e in faux.journal)


class TestNeedsRender:
    @pytest.mark.parametrize("valeur", [True, "true", "True", "oui", "yes", "1"])
    def test_reconnait_une_demande_de_rendu(self, valeur):
        assert needs_render({"render": valeur})

    @pytest.mark.parametrize("valeur", [False, None, "", "false", "non", 0])
    def test_par_defaut_pas_de_rendu(self, valeur):
        assert not needs_render({"render": valeur})
        assert not needs_render({})


class TestChromiumReel:
    """Ignoré quand Playwright ou Chromium manque sur le poste ; joué en CI."""

    PAGE = (
        "data:text/html,<html><head><title>Coquille</title></head><body>"
        "<div id='hote'></div>"
        "<script>"
        "document.title='Rendu';"
        "const racine=document.getElementById('hote').attachShadow({mode:'open'});"
        "racine.innerHTML='<h1>Titre dans le shadow DOM</h1><a href=\"/s/article/un\">Un article</a>';"
        "</script></body></html>"
    )

    def test_rend_une_page_et_traverse_le_shadow_dom(self):
        pytest.importorskip("playwright")
        session = BrowserSession(user_agent="VeilleRSS-tests/1.0")
        try:
            try:
                reponse = session.get(self.PAGE, timeout=30, wait_for="h1")
            except RuntimeError as exc:
                pytest.skip(f"Chromium indisponible : {exc}")
        finally:
            session.close()
        assert reponse.status_code == 200
        assert "<title>Rendu</title>" in reponse.text
        assert "<h1>Titre dans le shadow DOM</h1>" in reponse.text
        assert 'href="/s/article/un"' in reponse.text
