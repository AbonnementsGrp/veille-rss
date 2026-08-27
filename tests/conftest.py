"""Fixtures partagées : accès aux jeux de données de tests/fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_bytes():
    def _read(name: str) -> bytes:
        return (FIXTURES / name).read_bytes()
    return _read


@pytest.fixture
def fixture_text():
    def _read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")
    return _read
