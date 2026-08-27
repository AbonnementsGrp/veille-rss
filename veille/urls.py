"""Normalisation des URL d'articles.

Les liens servent d'identité à un article : c'est sur eux que reposent la
déduplication et l'`uid` de l'historique. Deux URL qui ne diffèrent que par
des paramètres de suivi désignent le même article et doivent donc converger.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Préfixes de paramètres de campagne : Matomo/Piwik (pk_, mtm_), Google (utm_).
TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "piwik_")
# Identifiants de clic ajoutés par les plateformes.
TRACKING_KEYS = frozenset({"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid"})


def is_tracking_param(key: str) -> bool:
    low = key.lower()
    return low.startswith(TRACKING_PREFIXES) or low in TRACKING_KEYS


def clean_link(url: str) -> str:
    """Retire les paramètres de suivi d'une URL, en conservant les autres.

    Les flux thématiques de Localtis, par exemple, marquent chaque lien d'un
    `pk_kwd` propre à la rubrique : sans ce nettoyage, un article publié dans
    deux rubriques apparaîtrait deux fois dans le flux consolidé.
    """
    url = (url or "").strip()
    if "?" not in url:
        return url
    parts = urlsplit(url)
    gardes = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not is_tracking_param(k)]
    return urlunsplit(parts._replace(query=urlencode(gardes)))
