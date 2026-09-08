"""Gestion des domaines de la veille : les rubriques du tableau de bord.

Les domaines vivent à deux endroits : `settings.themes` dans config/sites.yml,
qui dit quels domaines sont reconnus, et la liste déroulante du formulaire
d'issue « Proposer une nouvelle source ». Les deux doivent rester alignés. Ce
module est le seul à les modifier, et il les modifie ensemble. Renommer un
domaine touche un troisième endroit : la clé `theme` de chaque source qui s'y
rattache.

L'ordre d'affichage n'est plus une décision : il est alphabétique, partout. Les
listes sont donc réécrites triées à chaque modification.

Les fichiers ne sont pas repassés par le sérialiseur YAML, qui effacerait leurs
commentaires : seules les lignes concernées sont réécrites, dans le style de fin
de ligne du fichier, puis le résultat est relu pour vérifier qu'il dit bien ce
qu'on voulait.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from veille.config import CONFIG_PATH, ROOT, sort_key

FORM_PATH = ROOT / ".github" / "ISSUE_TEMPLATE" / "nouvelle-source.yml"
MAX_LENGTH = 40
# « Autres » est le domaine implicite des sources sans domaine reconnu.
RESERVED = {"autres"}

THEMES_HEADER = re.compile(r"^\s*themes:\s*$")
DOMAINE_ID = re.compile(r"^\s*id:\s*domaine\s*$")
OPTIONS_HEADER = re.compile(r"^\s*options:\s*$")
LIST_ITEM = re.compile(r"^(\s*)-\s+(.*)$")
SOURCE_THEME_LINE = re.compile(r"^(\s*theme:\s*)(.*)$")


@dataclass
class ThemePlan:
    """Ce qui serait fait : le nom retenu et la liste alphabétique qui en résulte."""

    name: str
    before: list[str]
    result: list[str]
    warnings: list[str] = field(default_factory=list)

    @property
    def position(self) -> int:
        return self.result.index(self.name) + 1


@dataclass
class RenamePlan:
    """Un domaine change de nom : l'ancien reconnu, le nouveau, la liste résultante."""

    old: str
    new: str
    before: list[str]
    result: list[str]

    @property
    def position(self) -> int:
        return self.result.index(self.new) + 1


def newline_of(text: str) -> str:
    """Le style de fin de ligne du fichier, pour le réécrire à l'identique."""
    return "\r\n" if "\r\n" in text else "\n"


def sorted_themes(themes: list[str]) -> list[str]:
    return sorted(themes, key=sort_key)


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


def resolve_theme(query: str, themes: list[str]) -> str:
    """Retrouve un domaine tel qu'il est écrit, à partir d'une saisie approximative.

    Casse et accents sont ignorés : « sante, social & seniors » désigne bien
    « Santé, social & séniors ». Le nom exact du fichier est rendu.
    """
    saisie = " ".join(query.split())
    if not saisie:
        raise ValueError("aucun nom de domaine fourni")
    exacts = [t for t in themes if t == saisie]
    if exacts:
        return exacts[0]
    proches = [t for t in themes if sort_key(t) == sort_key(saisie)]
    if len(proches) == 1:
        return proches[0]
    raise ValueError(f"aucun domaine « {saisie} » ; domaines existants : {', '.join(themes)}")


def validate_name(nom: str) -> str:
    nom = " ".join(nom.split())
    if len(nom) < 2:
        raise ValueError("le nom du domaine est vide ou trop court")
    if len(nom) > MAX_LENGTH:
        raise ValueError(f"le nom du domaine dépasse {MAX_LENGTH} caractères")
    if nom.casefold() in RESERVED:
        raise ValueError("« Autres » est réservé aux sources sans domaine reconnu")
    return nom


def plan_theme(name: str, themes: list[str] | None = None) -> ThemePlan:
    """Valide un nom de domaine et calcule la liste alphabétique qui en résulterait."""
    themes = list(themes if themes is not None else current_themes())
    nom = validate_name(name)
    if any(t.casefold() == nom.casefold() for t in themes):
        raise ValueError(f"le domaine « {nom} » existe déjà")
    return ThemePlan(name=nom, before=themes, result=sorted_themes(themes + [nom]))


def plan_rename(old: str, new: str, themes: list[str] | None = None) -> RenamePlan:
    """Valide un renommage : l'ancien nom doit exister, le nouveau ne pas être pris."""
    themes = list(themes if themes is not None else current_themes())
    ancien = resolve_theme(old, themes)
    nouveau = validate_name(new)
    if nouveau == ancien:
        raise ValueError(f"« {ancien} » est déjà le nom de ce domaine")
    if any(t.casefold() == nouveau.casefold() for t in themes if t != ancien):
        raise ValueError(f"le domaine « {nouveau} » existe déjà")
    restants = [t for t in themes if t != ancien]
    return RenamePlan(old=ancien, new=nouveau, before=themes, result=sorted_themes(restants + [nouveau]))


def unquote(valeur: str) -> str:
    """Retire les guillemets qui entourent une valeur YAML écrite en ligne."""
    valeur = valeur.strip()
    if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
        return valeur[1:-1]
    return valeur


def locate(lines: list[str], pattern: re.Pattern[str], start: int = 0) -> int:
    for i in range(start, len(lines)):
        if pattern.match(lines[i]):
            return i
    raise ValueError(f"ligne introuvable : {pattern.pattern}")


def list_items(lines: list[str], header_index: int) -> list[tuple[int, str]]:
    """Les éléments `- …` de la liste qui suit l'en-tête : (numéro de ligne, valeur).

    La liste s'arrête à la première ligne qui n'est plus indentée sous l'en-tête.
    Les lignes vides et les commentaires intercalés sont ignorés.
    """
    indent_entete = len(lines[header_index]) - len(lines[header_index].lstrip())
    elements: list[tuple[int, str]] = []
    for j in range(header_index + 1, len(lines)):
        ligne = lines[j]
        if ligne.strip() == "" or ligne.strip().startswith("#"):
            continue
        if len(ligne) - len(ligne.lstrip()) <= indent_entete:
            break
        correspondance = LIST_ITEM.match(ligne)
        if not correspondance:
            break
        elements.append((j, unquote(correspondance.group(2))))
    return elements


def replace_list_items(text: str, header_index: int, values: list[str]) -> str:
    """Remplace les éléments de la liste qui suit l'en-tête par `values`, dans l'ordre.

    Le bloc allant du premier au dernier élément est réécrit avec l'indentation
    existante ; tout ce qui précède l'en-tête ou suit la liste est intact.
    """
    nl = newline_of(text)
    lignes = text.split(nl)
    elements = list_items(lignes, header_index)
    if not elements:
        raise ValueError("la liste est vide ou n'a pas la forme attendue")
    indentation = " " * (len(lignes[elements[0][0]]) - len(lignes[elements[0][0]].lstrip()))
    nouvelles = [f'{indentation}- "{v.replace(chr(34), chr(39))}"' for v in values]
    lignes[elements[0][0]:elements[-1][0] + 1] = nouvelles
    return nl.join(lignes)


def retag_sources(text: str, old: str, new: str) -> tuple[str, int]:
    """Remplace `theme: "old"` par `theme: "new"` sur chaque source ; rend le texte et le nombre."""
    nl = newline_of(text)
    lignes = text.split(nl)
    compte = 0
    for i, ligne in enumerate(lignes):
        correspondance = SOURCE_THEME_LINE.match(ligne)
        if correspondance and unquote(correspondance.group(2)) == old:
            lignes[i] = f'{correspondance.group(1)}"{new.replace(chr(34), chr(39))}"'
            compte += 1
    return nl.join(lignes), compte


def check_form_alignment(form_path: Path, before: list[str]) -> None:
    if sorted_themes(form_themes(form_path)) != sorted_themes(before):
        raise ValueError("la liste déroulante du formulaire diffère de settings.themes : "
                         "réaligner les deux avant de modifier un domaine")


def rewrite_lists(config_text: str, form_text: str, themes: list[str]) -> tuple[str, str]:
    """Réécrit la liste des domaines dans la configuration et dans le formulaire."""
    config_lines = config_text.split(newline_of(config_text))
    nouveau_config = replace_list_items(config_text, locate(config_lines, THEMES_HEADER), themes)
    form_lines = form_text.split(newline_of(form_text))
    debut = locate(form_lines, DOMAINE_ID)
    nouveau_form = replace_list_items(form_text, locate(form_lines, OPTIONS_HEADER, debut), themes)
    return nouveau_config, nouveau_form


def reread_lists(config_text: str, form_text: str) -> tuple[list[str], list[str]]:
    relu_config = [str(t) for t in yaml.safe_load(config_text)["settings"]["themes"]]
    relu_form = [str(o) for b in yaml.safe_load(form_text)["body"] if b.get("id") == "domaine"
                 for o in b["attributes"]["options"]]
    return relu_config, relu_form


def add_theme(plan: ThemePlan, config_path: Path | None = None, form_path: Path | None = None) -> None:
    """Écrit la liste résultante dans la configuration et dans le formulaire, ou dans aucun des deux."""
    config_path = Path(config_path or CONFIG_PATH)
    form_path = Path(form_path or FORM_PATH)
    check_form_alignment(form_path, plan.before)

    nouveau_config, nouveau_form = rewrite_lists(
        config_path.read_text(encoding="utf-8"), form_path.read_text(encoding="utf-8"), plan.result)
    relu_config, relu_form = reread_lists(nouveau_config, nouveau_form)
    if relu_config != plan.result or relu_form != plan.result:
        raise ValueError("après réécriture, les fichiers ne relisent pas la liste attendue")

    config_path.write_text(nouveau_config, encoding="utf-8")
    form_path.write_text(nouveau_form, encoding="utf-8")


def rename_theme(plan: RenamePlan, config_path: Path | None = None, form_path: Path | None = None) -> int:
    """Renomme un domaine partout : liste, sources qui s'y rattachent, formulaire.

    Rend le nombre de sources rattachées au nouveau nom. Rien n'est écrit si
    l'une des relectures ne confirme pas le résultat attendu.
    """
    config_path = Path(config_path or CONFIG_PATH)
    form_path = Path(form_path or FORM_PATH)
    check_form_alignment(form_path, plan.before)

    config_text = config_path.read_text(encoding="utf-8")
    nouveau_config, nouveau_form = rewrite_lists(config_text, form_path.read_text(encoding="utf-8"), plan.result)
    nouveau_config, retaguees = retag_sources(nouveau_config, plan.old, plan.new)

    relu_config, relu_form = reread_lists(nouveau_config, nouveau_form)
    sites = yaml.safe_load(nouveau_config).get("sites") or []
    if relu_config != plan.result or relu_form != plan.result:
        raise ValueError("après réécriture, les fichiers ne relisent pas la liste attendue")
    if any(s.get("theme") == plan.old for s in sites):
        raise ValueError("une source porte encore l'ancien nom après réécriture")
    if sum(1 for s in sites if s.get("theme") == plan.new) != retaguees:
        raise ValueError("le nombre de sources rattachées au nouveau nom ne correspond pas")

    config_path.write_text(nouveau_config, encoding="utf-8")
    form_path.write_text(nouveau_form, encoding="utf-8")
    return retaguees


__all__ = [
    "FORM_PATH", "RenamePlan", "ThemePlan", "add_theme", "current_themes", "form_themes",
    "list_items", "newline_of", "plan_rename", "plan_theme", "rename_theme", "replace_list_items",
    "resolve_theme", "retag_sources", "sorted_themes",
]
