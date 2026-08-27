"""Nettoyage des textes extraits des flux et des pages."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


def clean_text(value: Any, limit: int = 1800) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", value).strip()[:limit]
