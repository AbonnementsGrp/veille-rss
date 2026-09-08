"""Lot de certificats : certifi complété des intermédiaires du dépôt."""

from __future__ import annotations

import ssl
from pathlib import Path

import certifi
import pytest

from veille.fetch import CERTS_DIR, ENV_BUNDLE_VARS, ca_bundle, extra_certificates, pem_blocks, request_session


def faux_pem(corps: str) -> str:
    return f"-----BEGIN CERTIFICATE-----\n{corps}\n-----END CERTIFICATE-----\n"


@pytest.fixture
def sans_lot_d_environnement(monkeypatch):
    for nom in ENV_BUNDLE_VARS:
        monkeypatch.delenv(nom, raising=False)


class TestLotDeCertificats:
    def test_sans_complement_le_lot_est_celui_de_certifi(self, tmp_path: Path, sans_lot_d_environnement):
        vide = tmp_path / "certs"
        vide.mkdir()
        assert ca_bundle(vide, tmp_path / "cache") == certifi.where()
        assert ca_bundle(tmp_path / "absent", tmp_path / "cache") == certifi.where()

    def test_le_lot_fusionne_commence_par_certifi_et_finit_par_les_complements(self, tmp_path: Path, sans_lot_d_environnement):
        certs = tmp_path / "certs"
        certs.mkdir()
        (certs / "b-second.pem").write_text(faux_pem("SECONDCERTIFICAT"), encoding="ascii")
        (certs / "a-premier.pem").write_text(faux_pem("PREMIERCERTIFICAT"), encoding="ascii")
        (certs / "lisez-moi.txt").write_text("ignoré", encoding="utf-8")

        lot = Path(ca_bundle(certs, tmp_path / "cache"))

        assert lot.parent == tmp_path / "cache"
        blocs = pem_blocks(lot.read_bytes())
        assert blocs[:-2] == pem_blocks(Path(certifi.where()).read_bytes()), "certifi d'abord, intégralement"
        assert b"PREMIERCERTIFICAT" in blocs[-2] and b"SECONDCERTIFICAT" in blocs[-1], (
            "les compléments suivent l'ordre alphabétique des fichiers")

    def test_le_lot_est_reutilise_puis_reecrit_si_un_certificat_change(self, tmp_path: Path, sans_lot_d_environnement):
        certs = tmp_path / "certs"
        certs.mkdir()
        (certs / "un.pem").write_text(faux_pem("UNCERTIFICAT"), encoding="ascii")
        cache = tmp_path / "cache"

        premier = ca_bundle(certs, cache)
        horodatage = Path(premier).stat().st_mtime_ns
        assert ca_bundle(certs, cache) == premier
        assert Path(premier).stat().st_mtime_ns == horodatage, "un lot inchangé n'est pas réécrit"

        Path(premier).write_bytes(b"corrompu")
        assert Path(ca_bundle(certs, cache)).read_bytes() != b"corrompu", "un lot altéré est reconstruit"

        (certs / "deux.pem").write_text(faux_pem("AUTRECERTIFICAT"), encoding="ascii")
        second = ca_bundle(certs, cache)
        assert second != premier, "le nom du lot suit son contenu"
        assert b"AUTRECERTIFICAT" in Path(second).read_bytes()

    def test_le_lot_designe_par_l_environnement_est_integre_sans_doublon(self, tmp_path: Path, monkeypatch, sans_lot_d_environnement):
        certifi_blocs = pem_blocks(Path(certifi.where()).read_bytes())
        lot_poste = tmp_path / "ca-bundle.crt"
        # Un lot de poste : une racine déjà connue de certifi, plus une autorité interne.
        lot_poste.write_bytes(certifi_blocs[0] + b"\n" + faux_pem("AUTORITEINTERNE").encode("ascii"))
        monkeypatch.setenv("CURL_CA_BUNDLE", str(lot_poste))
        certs = tmp_path / "certs"
        certs.mkdir()
        (certs / "intermediaire.pem").write_text(faux_pem("INTERMEDIAIRE"), encoding="ascii")

        contenu = Path(ca_bundle(certs, tmp_path / "cache")).read_bytes()

        assert b"AUTORITEINTERNE" in contenu, "l'autorité du poste est conservée"
        assert b"INTERMEDIAIRE" in contenu, "nos compléments aussi"
        assert len(pem_blocks(contenu)) == len(certifi_blocs) + 2, "la racine commune n'est comptée qu'une fois"

    def test_une_variable_vers_un_fichier_absent_est_ignoree(self, tmp_path: Path, monkeypatch, sans_lot_d_environnement):
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(tmp_path / "nulle-part.crt"))
        vide = tmp_path / "certs"
        vide.mkdir()
        assert ca_bundle(vide, tmp_path / "cache") == certifi.where()


class TestCertificatsDuDepot:
    def test_le_depot_fournit_l_intermediaire_digicert_manquant_d_anap(self):
        noms = [p.name for p in extra_certificates()]
        assert "digicert-global-g2-tls-rsa-sha256-2020-ca1.pem" in noms

    def test_chaque_certificat_du_depot_est_un_pem_lisible_par_openssl(self):
        certificats = extra_certificates()
        assert certificats, "config/certs ne doit pas être vide tant qu'un site a besoin d'un complément"
        for chemin in certificats:
            texte = chemin.read_text(encoding="ascii")
            assert texte.startswith("-----BEGIN CERTIFICATE-----"), chemin.name
            contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # vide : sans les racines du système
            contexte.load_verify_locations(cafile=str(chemin))  # lève ssl.SSLError si le PEM est altéré
            assert contexte.cert_store_stats()["x509"] == 1, chemin.name

    def test_le_lot_complet_se_charge_dans_un_contexte_tls(self):
        contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        contexte.load_verify_locations(cafile=ca_bundle())
        stats = contexte.cert_store_stats()
        assert stats["x509"] > 100, "le lot garde toutes les racines de certifi"
        assert CERTS_DIR.is_dir()


class TestSession:
    def test_la_session_verifie_les_sites_avec_le_lot_fusionne(self):
        session = request_session({"user_agent": "Test/1.0"})
        assert session.verify == ca_bundle()
        assert Path(str(session.verify)).is_file()
        assert session.headers["User-Agent"] == "Test/1.0"

    def test_une_variable_d_environnement_n_ecrase_pas_le_lot_de_la_session(self, tmp_path: Path, monkeypatch):
        lot_poste = tmp_path / "ca-bundle.crt"
        lot_poste.write_text(faux_pem("AUTORITEINTERNE"), encoding="ascii")
        monkeypatch.setenv("CURL_CA_BUNDLE", str(lot_poste))
        session = request_session({})

        reglages = session.merge_environment_settings("https://exemple.fr/", {}, None, None, None)

        assert reglages["verify"] == session.verify
        assert b"AUTORITEINTERNE" in Path(str(session.verify)).read_bytes()
        explicite = session.merge_environment_settings("https://exemple.fr/", {}, None, str(lot_poste), None)
        assert explicite["verify"] == str(lot_poste), "une consigne explicite par requête reste respectée"
