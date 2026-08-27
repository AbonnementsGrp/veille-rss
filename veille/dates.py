"""Normalisation et comparaison des dates.

Toutes les dates manipulées par le projet sont stockées en ISO 8601 UTC.
Les flux sources, eux, mélangent RFC-822, ISO et dates en clair : c'est ici
que cette diversité est absorbée.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

from veille.models import Item

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class FrenchParserInfo(date_parser.parserinfo):
    """Apprend les noms de mois et de jours français à dateutil.

    Les pages d'actualités françaises datent leurs articles en clair
    ("25 juin 2026"), forme que le parseur par défaut, anglophone, rejette.
    Les libellés anglais sont conservés : les flux RSS s'en servent.
    """

    WEEKDAYS = [
        ("Mon", "Monday", "lundi", "lun"),
        ("Tue", "Tuesday", "mardi", "mar"),
        ("Wed", "Wednesday", "mercredi", "mer"),
        ("Thu", "Thursday", "jeudi", "jeu"),
        ("Fri", "Friday", "vendredi", "ven"),
        ("Sat", "Saturday", "samedi", "sam"),
        ("Sun", "Sunday", "dimanche", "dim"),
    ]
    MONTHS = [
        ("Jan", "January", "janvier", "janv"),
        ("Feb", "February", "février", "fevrier", "févr", "fevr"),
        ("Mar", "March", "mars"),
        ("Apr", "April", "avril", "avr"),
        ("May", "May", "mai"),
        ("Jun", "June", "juin"),
        ("Jul", "July", "juillet", "juil"),
        ("Aug", "August", "août", "aout"),
        ("Sep", "Sept", "September", "septembre", "sept"),
        ("Oct", "October", "octobre"),
        ("Nov", "November", "novembre"),
        ("Dec", "December", "décembre", "decembre", "déc"),
    ]


FRENCH = FrenchParserInfo(dayfirst=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str) -> datetime | None:
    """Lit une date déjà normalisée sans l'ambiguïté jour/mois de dateutil.

    `dayfirst=True` est indispensable pour les dates françaises en clair, mais
    il inverse jour et mois sur une chaîne ISO ("2026-07-10" -> 10 juillet lu
    comme 10e mois). L'ISO doit donc être reconnu en premier.
    """
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def normalize_date(value: Any) -> str:
    """Rend une date sous forme ISO 8601 UTC, ou "" si elle est illisible."""
    if not value:
        return ""
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (tuple, list)) and len(value) >= 6:
            dt = datetime(*value[:6], tzinfo=timezone.utc)
        else:
            text = str(value)
            dt = parse_iso(text) or date_parser.parse(text, FRENCH, dayfirst=True, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def parse_date_for_feed(value: str) -> datetime | None:
    """Rend un datetime conscient du fuseau, ou None si la date est illisible."""
    if not value:
        return None
    try:
        dt = parse_iso(value) or date_parser.parse(value, FRENCH)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def item_sort_key(item: Item) -> datetime:
    """Clé de tri d'un article : sa date de publication, sinon sa découverte.

    Renvoie un datetime et non une chaîne : comparer des chaînes de formats
    différents plaçait les dates RFC-822 avant toutes les dates ISO.
    """
    return parse_date_for_feed(item.published) or parse_date_for_feed(item.first_seen) or EPOCH
