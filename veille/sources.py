"""Suppression d'une source de la veille.

Une source vit à trois endroits : son bloc dans config/sites.yml, ses articles
dans data/history.json, et son flux publié dans public/. Supprimer la source,
c'est retirer les trois — sinon le flux resterait en ligne, figé, et
l'historique garderait soixante articles d'une source qui n'existe plus.

Le bloc de configuration est retiré du texte, pas via le sérialiseur YAML, afin
de préserver les commentaires du fichier. Le résultat est relu pour vérifier que
la source a bien disparu et qu'aucune autre n'a bougé.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from veille.config import CONFIG_PATH, HISTORY_PATH, PUBLIC_DIR, display_name, load_config, sort_key
from veille.history import load_history, remove_source, save_history
from veille.pipeline import output_name_for
from veille.themes import newline_of, unquote

BLOCK_START = re.compile(r"^(\s*)-\s+name:\s*(.*)$")


@dataclass
class RemovalPlan:
    """Ce qui serait retiré : la source reconnue et ce qu'elle laisse derrière elle."""

    name: str
    short_name: str
    theme: str
    url: str
    output: str
    history_entries: int
    feed_exists: bool


def find_source(query: str, sites: list[dict[str, Any]]) -> dict[str, Any]:
    """Retrouve une source par son nom complet ou son nom court.

    La saisie exacte l'emporte ; à défaut, casse et accents sont ignorés. Une
    saisie qui désigne plusieurs sources, ou aucune, est refusée avec la liste
    des noms affichés pour aider à corriger.
    """
    saisie = " ".join(query.split())
    if not saisie:
        raise ValueError("aucun nom de source fourni")
    exacts = [s for s in sites if s["name"] == saisie or s.get("short_name") == saisie]
    if len(exacts) == 1:
        return exacts[0]
    cle = sort_key(saisie)
    proches = [s for s in sites if sort_key(s["name"]) == cle or sort_key(str(s.get("short_name") or "")) == cle]
    if len(proches) == 1:
        return proches[0]
    noms = ", ".join(display_name(s) for s in sites)
    if not proches and not exacts:
        raise ValueError(f"aucune source nommée « {saisie} » ; sources suivies : {noms}")
    raise ValueError(f"plusieurs sources correspondent à « {saisie} » : préciser le nom complet")


def plan_removal(query: str, cfg: dict[str, Any] | None = None, history: dict[str, Any] | None = None,
                 public_dir: Path | None = None) -> RemovalPlan:
    cfg = cfg or load_config()
    site = find_source(query, cfg["sites"])
    history = history if history is not None else load_history()
    output = str(site.get("output") or output_name_for(site))
    return RemovalPlan(
        name=site["name"], short_name=display_name(site), theme=str(site.get("theme") or "Autres"),
        url=str(site.get("url", "")), output=output,
        history_entries=sum(1 for r in history.values() if r.get("source") == site["name"]),
        feed_exists=(Path(public_dir or PUBLIC_DIR) / output).exists(),
    )


def remove_source_block(text: str, name: str) -> str:
    """Retire du texte le bloc `- name: "<name>"` et tout ce qui lui appartient.

    Le bloc court de sa ligne `- name:` jusqu'à la ligne suivante qui n'est plus
    indentée sous lui — le bloc suivant, ou la fin du fichier — en emportant les
    lignes vides qui le séparaient du suivant.
    """
    nl = newline_of(text)
    lignes = text.split(nl)
    debuts = [i for i, l in enumerate(lignes)
              if (m := BLOCK_START.match(l)) and unquote(m.group(2)) == name]
    if len(debuts) != 1:
        raise ValueError(f"bloc de la source « {name} » introuvable ou en double dans le fichier")
    debut = debuts[0]
    indent = len(lignes[debut]) - len(lignes[debut].lstrip())
    fin = len(lignes)
    for j in range(debut + 1, len(lignes)):
        ligne = lignes[j]
        if ligne.strip() and not ligne.lstrip().startswith("#") and len(ligne) - len(ligne.lstrip()) <= indent:
            fin = j
            break
    del lignes[debut:fin]
    while lignes and lignes[-1].strip() == "":
        lignes.pop()
    return nl.join(lignes) + nl


def apply_removal(plan: RemovalPlan, config_path: Path | None = None, history_path: Path | None = None,
                  public_dir: Path | None = None, history_limit: int = 1000) -> None:
    """Retire la source de la configuration, de l'historique et du dossier publié."""
    config_path = Path(config_path or CONFIG_PATH)
    history_path = Path(history_path or HISTORY_PATH)
    public_dir = Path(public_dir or PUBLIC_DIR)

    texte = config_path.read_text(encoding="utf-8")
    avant = yaml.safe_load(texte).get("sites") or []
    nouveau = remove_source_block(texte, plan.name)
    apres = yaml.safe_load(nouveau).get("sites") or []
    if len(apres) != len(avant) - 1 or any(s.get("name") == plan.name for s in apres):
        raise ValueError("après retrait, le fichier ne relit pas la liste attendue")
    if [s["name"] for s in apres] != [s["name"] for s in avant if s["name"] != plan.name]:
        raise ValueError("le retrait a déplacé une autre source : abandon")

    config_path.write_text(nouveau, encoding="utf-8")
    history = load_history(history_path)
    remove_source(history, plan.name)
    save_history(history, history_limit, history_path)
    flux = public_dir / plan.output
    if flux.exists():
        flux.unlink()


__all__ = ["RemovalPlan", "apply_removal", "find_source", "plan_removal", "remove_source_block"]
