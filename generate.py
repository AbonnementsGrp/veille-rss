#!/usr/bin/env python3
"""Point d'entrée de la veille RSS.

    python generate.py

Lit `config/sites.yml`, interroge chaque source, écrit les flux et le tableau
de bord dans `public/`, met à jour `data/history.json`. Le traitement lui-même
vit dans le package `veille/`.
"""

from __future__ import annotations

import logging
import sys

from veille.pipeline import run

LOG_FORMAT = "%(levelname)s | %(message)s"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    return run()


if __name__ == "__main__":
    sys.exit(main())
