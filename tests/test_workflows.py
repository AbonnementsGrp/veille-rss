"""Étape d'étiquetage des workflows d'issue, exécutée avec un faux `gh`."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"

# Ce que chaque script d'enquête peut écrire dans verdict.txt, et l'étiquette que
# l'issue doit porter ensuite.
VERDICTS_SOURCE = {"ok": "enquete-ok", "a_verifier": "enquete-a-verifier",
                   "manuel": "enquete-manuel", "erreur": "enquete-erreur"}
VERDICTS_DEMANDE = {"ok": "enquete-ok", "erreur": "enquete-erreur"}
VERDICTS = {
    "nouvelle-source.yml": VERDICTS_SOURCE,
    "nouveau-domaine.yml": VERDICTS_DEMANDE,
    "renommer-domaine.yml": VERDICTS_DEMANDE,
    "supprimer-domaine.yml": VERDICTS_DEMANDE,
    "supprimer-source.yml": VERDICTS_DEMANDE,
}
CAS = [(workflow, verdict) for workflow, verdicts in VERDICTS.items() for verdict in verdicts]

# Le faux gh consigne chaque appel sur une ligne, arguments séparés par \x1f.
FAUX_GH = "gh() { printf '%s\\037' \"$@\" >> gh.log; printf '\\n' >> gh.log; }\n"


def bash() -> str:
    chemin = shutil.which("bash")
    # Le lanceur WSL de System32 n'est pas un bash utilisable sans distribution.
    if not chemin or Path(chemin).parent.name.lower() == "system32":
        pytest.skip("bash indisponible")
    return chemin


def etape_d_etiquetage(workflow: str) -> str:
    """Le script de l'étape qui étiquette l'issue d'après verdict.txt."""
    donnees = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    for job in donnees["jobs"].values():
        for etape in job.get("steps", []):
            script = etape.get("run", "")
            if "verdict.txt" in script and "gh issue edit" in script:
                return script
    raise AssertionError(f"{workflow} : aucune étape d'étiquetage")


@pytest.fixture(scope="module")
def etiquetage(tmp_path_factory):
    """Lance l'étape une fois par workflow et par verdict ; rend les étiquettes
    posées et retirées par son `gh issue edit`."""
    resultats: dict[tuple[str, str], dict[str, list[str]]] = {}

    def lancer(workflow: str, verdict: str) -> dict[str, list[str]]:
        if (workflow, verdict) not in resultats:
            dossier = tmp_path_factory.mktemp(verdict)
            (dossier / "verdict.txt").write_text(verdict, encoding="utf-8")
            (dossier / "commentaire.md").write_text("Résultat de l'enquête\n", encoding="utf-8")
            (dossier / "etape.sh").write_text(FAUX_GH + etape_d_etiquetage(workflow),
                                              encoding="utf-8", newline="\n")
            subprocess.run([bash(), "-e", "etape.sh"], cwd=dossier, check=True, timeout=60,
                           env={**os.environ, "NUMERO": "14", "AUTO": "false", "GH_TOKEN": "factice"})
            appels = [ligne.split("\x1f")[:-1]
                      for ligne in (dossier / "gh.log").read_text(encoding="utf-8").splitlines()]
            edition = next(a for a in appels if a[:2] == ["issue", "edit"])
            options: dict[str, list[str]] = {"--add-label": [], "--remove-label": []}
            for option, valeur in zip(edition, edition[1:]):
                if option in options:
                    options[option] += [e for e in valeur.split(",") if e]
            resultats[(workflow, verdict)] = options
        return resultats[(workflow, verdict)]

    return lancer


@pytest.mark.parametrize("workflow, verdict", CAS, ids=[f"{w}-{v}" for w, v in CAS])
def test_l_etiquette_du_verdict_n_est_pas_retiree_par_l_appel_qui_la_pose(etiquetage, workflow, verdict):
    """gh pose et retire les étiquettes d'un même `gh issue edit` par deux requêtes
    parallèles (cli/cli, pkg/cmd/pr/shared/editable_http.go) : une étiquette
    présente des deux côtés disparaît quand le retrait arrive en second. Les
    issues #8 et #14 sont ainsi restées sans étiquette de verdict."""
    etiquette = VERDICTS[workflow][verdict]
    appel = etiquetage(workflow, verdict)
    assert etiquette in appel["--add-label"]
    assert etiquette not in appel["--remove-label"]


@pytest.mark.parametrize("workflow, verdict", CAS, ids=[f"{w}-{v}" for w, v in CAS])
def test_les_etiquettes_des_autres_verdicts_sont_retirees(etiquetage, workflow, verdict):
    """Une enquête relancée remplace le verdict précédent au lieu de s'y ajouter."""
    autres = set(VERDICTS[workflow].values()) - {VERDICTS[workflow][verdict]}
    assert set(etiquetage(workflow, verdict)["--remove-label"]) == autres
