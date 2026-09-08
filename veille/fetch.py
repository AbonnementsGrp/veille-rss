"""Session HTTP partagée, lot de certificats et reconnaissance d'un flux."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import certifi
import requests

from veille.config import ROOT

# Certificats intermédiaires que certains sites oublient d'envoyer. Un fichier
# PEM par certificat ; tous complètent le lot de certifi, aucun ne le remplace.
CERTS_DIR = ROOT / "config" / "certs"

# Variables par lesquelles requests et curl désignent un lot de certificats.
# Un poste d'entreprise peut en poser une (PostgreSQL pose CURL_CA_BUNDLE) : le
# lot qu'elle désigne est intégré au nôtre, jamais perdu ni laissé seul.
ENV_BUNDLE_VARS = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE")

PEM_BLOCK = re.compile(b"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


def extra_certificates(certs_dir: Path | None = None) -> list[Path]:
    dossier = certs_dir or CERTS_DIR
    if not dossier.is_dir():
        return []
    return sorted(p for p in dossier.glob("*.pem") if p.is_file())


def environment_bundle() -> Path | None:
    for nom in ENV_BUNDLE_VARS:
        valeur = os.environ.get(nom, "").strip()
        if valeur and Path(valeur).is_file():
            return Path(valeur)
    return None


def pem_blocks(contenu: bytes) -> list[bytes]:
    return PEM_BLOCK.findall(contenu)


def ca_bundle(certs_dir: Path | None = None, cache_dir: Path | None = None) -> str:
    """Chemin du lot de certificats servant à vérifier les sites.

    Le lot de certifi, puis celui que l'environnement désigne s'il y en a un,
    puis les certificats de config/certs, sans doublon. Sans complément d'aucune
    sorte, c'est le lot de certifi lui-même. Le lot fusionné est écrit dans le
    dossier temporaire sous un nom dérivé de son contenu : réutilisé tel quel
    d'une exécution à l'autre, réécrit dès qu'un certificat change. La
    vérification reste entière : un site dont la chaîne ne remonte à aucune
    racine connue est toujours refusé.
    """
    sources = [Path(certifi.where())]
    environnement = environment_bundle()
    if environnement and environnement.resolve() != sources[0].resolve():
        sources.append(environnement)
    sources += extra_certificates(certs_dir)
    if len(sources) == 1:
        return certifi.where()

    blocs: list[bytes] = []
    vus: set[bytes] = set()
    for source in sources:
        for bloc in pem_blocks(source.read_bytes()):
            normalise = b"".join(bloc.split())
            if normalise not in vus:
                vus.add(normalise)
                blocs.append(bloc)
    contenu = b"\n".join(bloc.strip() + b"\n" for bloc in blocs)
    empreinte = hashlib.sha256(contenu).hexdigest()[:16]
    cible = (cache_dir or Path(tempfile.gettempdir())) / f"veille-ca-bundle-{empreinte}.pem"
    if not cible.exists() or cible.read_bytes() != contenu:
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(contenu)
    return str(cible)


class VeilleSession(requests.Session):
    """Session dont le lot de certificats prime sur l'environnement.

    requests laisse REQUESTS_CA_BUNDLE et CURL_CA_BUNDLE écraser le réglage
    `verify` d'une session : un poste où l'une d'elles est posée perdrait nos
    compléments. Le lot de la session, qui intègre déjà celui de
    l'environnement, l'emporte donc pour toute requête sans consigne explicite.
    """

    def merge_environment_settings(self, url, proxies, stream, verify, cert):
        reglages = super().merge_environment_settings(url, proxies, stream, verify, cert)
        if verify is None or verify is True:
            reglages["verify"] = self.verify
        return reglages


def request_session(settings: dict[str, Any]) -> requests.Session:
    session = VeilleSession()
    session.headers.update({
        "User-Agent": settings.get("user_agent", "VeilleRSS/1.0"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
        "Cache-Control": "no-cache",
    })
    session.verify = ca_bundle()
    return session


def is_feed_content(response: requests.Response) -> bool:
    """Détecte un flux RSS/Atom, y compris servi avec un content-type erroné."""
    content_type = response.headers.get("content-type", "").lower()
    head = response.text[:1000].lower()
    return any(x in content_type for x in ("rss", "atom", "xml")) or "<rss" in head or "<feed" in head
