"""Gestion des domaines de la veille : les rubriques du tableau de bord.

Les domaines vivent à deux endroits : `settings.themes` dans config/sites.yml,
qui fixe leur ordre d'affichage, et la liste déroulante du formulaire d'issue
« Proposer une nouvelle source ». Les deux doivent rester alignés. Ce module est
le seul à les modifier, et il les modifie ensemble.

Les fichiers ne sont pas repassés par le sérialiseur YAML, qui effacerait leurs
commentaires : la nouvelle ligne est insérée dans le texte, puis le résultat est
relu pour vérifier qu'il dit bien ce qu'on voulait.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from veille.config import CONFIG_PATH, ROOT

FORM_PATH = ROOT / ".github" / "ISSUE_TEMPLATE" / "nouvelle-source.yml"
MAX_LENGTH = 40
# « Autres » est le domaine implicite des sources sans domaine reconnu.
RESERVED = {"autres"}

THEMES_HEADER = re.compile(r"^\s*themes:\s*$")
DOMAINE_ID = re.compile(r"^\s*id:\s*domaine\s*$")
OPTIONS_HEADER = re.compile(r"^\s*options:\s*$")
LIST_ITEM = re.compile(r"^(\s*)-\s+(.*)$")


def unquote(valeur: str) -> str:
    """Retire les guillemets qui entourent une valeur YAML écrite en ligne."""
    valeur = valeur.strip()
    if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
        return valeur[1:-1]
    return valeur


@dataclass
class ThemePlan:
    """Ce qui serait fait : le nom retenu, sa place, et la liste résultante."""

    name: str
    after: str
    before: list[str]
    result: list[str]
    warnings: list[str] = field(default_factory=list)

    @property
    def position(self) -> int:
        return self.result.index(self.name) + 1


def current_themes(config_path: Path | None = None) -> list[str]:
    cfg = yaml.safe_load(Path(config_path or CONFIG_PATH).read_text(encoding="utf-8")) or {}
    return [str(t) for t in ((cfg.get("settings") or {}).get("themes") or [])]


def form_themes(form_path: Path | None = None) -> list[str]:
    """Les domaines offerts par la liste déroulante du formulaire de source."""
    data = yaml.safe_load(Path(form_path or FORM_PATH).read_text(encoding="utf-8")) or {}
    for bloc in data.get("body") or []:
        if bloc.get("id") == "domaine":
            return [str(o) for o in (bloc.get("attributes") or {}).get("options") or []]
    return []


def plan_theme(name: str, after: str = "", themes: list[str] | None = None) -> ThemePlan:
    """Valide un nom de domaine et calcule la liste qui en résulterait."""
    themes = list(themes if themes is not None else current_themes())
    nom = " ".join(name.split())
    if len(nom) < 2:
        raise ValueError("le nom du domaine est vide ou trop court")
    if len(nom) > MAX_LENGTH:
        raise ValueError(f"le nom du domaine dépasse {MAX_LENGTH} caractères")
    if nom.casefold() in RESERVED:
        raise ValueError("« Autres » est réservé aux sources sans domaine reconnu")
    if any(t.casefold() == nom.casefold() for t in themes):
        raise ValueError(f"le domaine « {nom} » existe déjà")

    apres = " ".join(after.split())
    if apres:
        correspondants = [t for t in themes if t.casefold() == apres.casefold()]
        if not correspondants:
            raise ValueError(f"aucun domaine « {apres} » après lequel placer le nouveau ; "
                             f"domaines existants : {', '.join(themes)}")
        apres = correspondants[0]
        position = themes.index(apres) + 1
    else:
        position = len(themes)
    return ThemePlan(name=nom, after=apres, before=themes, result=themes[:position] + [nom] + themes[position:])


def locate(lines: list[str], pattern: re.Pattern[str], start: int = 0) -> int:
    for i in range(start, len(lines)):
        if pattern.match(lines[i]):
            return i
    raise ValueError(f"ligne introuvable : {pattern.pattern}")


def insert_list_item(text: str, header_index: int, value: str, after: str = "") -> str:
    """Insère `- "value"` dans la liste YAML qui suit la ligne d'en-tête donnée.

    Les éléments sont les lignes `- …` plus indentées que l'en-tête, jusqu'à la
    première ligne qui ne l'est plus. Le reste du texte n'est pas touché.
    """
    lignes = text.split("\n")
    indent_entete = len(lignes[header_index]) - len(lignes[header_index].lstrip())
    elements: list[tuple[int, str]] = []
    j = header_index + 1
    while j < len(lignes):
        ligne = lignes[j]
        if ligne.strip() == "" or ligne.strip().startswith("#"):
            j += 1
            continue
        if len(ligne) - len(ligne.lstrip()) <= indent_entete:
            break
        correspondance = LIST_ITEM.match(ligne)
        if not correspondance:
            break
        elements.append((j, unquote(correspondance.group(2))))
        j += 1
    if not elements:
        raise ValueError("la liste est vide ou n'a pas la forme attendue")

    indentation = " " * (len(lignes[elements[0][0]]) - len(lignes[elements[0][0]].lstrip()))
    nouvelle = f'{indentation}- "{value.replace(chr(34), chr(39))}"'
    if after:
        cible = next((i for i, v in elements if v.casefold() == after.casefold()), None)
        if cible is None:
            raise ValueError(f"élément « {after} » introuvable dans la liste")
        lignes.insert(cible + 1, nouvelle)
    else:
        lignes.insert(elements[-1][0] + 1, nouvelle)
    return "\n".join(lignes)


def add_theme(plan: ThemePlan, config_path: Path | None = None, form_path: Path | None = None) -> None:
    """Écrit le domaine dans la configuration et dans le formulaire, ou dans aucun des deux."""
    config_path = Path(config_path or CONFIG_PATH)
    form_path = Path(form_path or FORM_PATH)

    if form_themes(form_path) != plan.before:
        raise ValueError("la liste déroulante du formulaire diffère de settings.themes : "
                         "réaligner les deux avant d'ajouter un domaine")

    config_text = config_path.read_text(encoding="utf-8")
    config_lines = config_text.split("\n")
    nouveau_config = insert_list_item(config_text, locate(config_lines, THEMES_HEADER), plan.name, plan.after)

    form_text = form_path.read_text(encoding="utf-8")
    form_lines = form_text.split("\n")
    debut = locate(form_lines, DOMAINE_ID)
    nouveau_form = insert_list_item(form_text, locate(form_lines, OPTIONS_HEADER, debut), plan.name, plan.after)

    relu_config = [str(t) for t in yaml.safe_load(nouveau_config)["settings"]["themes"]]
    relu_form = [str(o) for b in yaml.safe_load(nouveau_form)["body"] if b.get("id") == "domaine"
                 for o in b["attributes"]["options"]]
    if relu_config != plan.result or relu_form != plan.result:
        raise ValueError("après insertion, les fichiers ne relisent pas la liste attendue")

    config_path.write_text(nouveau_config, encoding="utf-8")
    form_path.write_text(nouveau_form, encoding="utf-8")


__all__ = ["FORM_PATH", "ThemePlan", "add_theme", "current_themes", "form_themes", "insert_list_item", "plan_theme"]
