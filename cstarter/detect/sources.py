"""Le détecteur de sources seules, celui de create.

Il lit un dossier sans configuration et propose des targets. Le type vient des
points d'entrée : main ou wmain pour un exécutable console, WinMain ou wWinMain pour
un exécutable fenêtré (y compris sous leur forme TCHAR, _tmain et _tWinMain), DllMain
ou __declspec(dllexport) pour une DLL, rien de tout cela pour une bibliothèque
statique. Une recherche textuelle se trompe sur une macro, un commentaire ou un bloc
#if : c'est une suggestion, que l'utilisateur confirme, par create comme par detect.

Un target par dossier de premier niveau qui contient des sources, quand la racine
n'en contient aucune et que ces dossiers sont plusieurs. Sinon, un seul target pour
tout le dossier.

La détection fine : le dossier include/ d'un target
devient ses public_headers, et un #include qui désigne un header public d'une
bibliothèque lie le target à elle. Un lien qui fermerait un cycle est signalé, pas créé.
"""

import posixpath
import re
from pathlib import Path

from cstarter import config
from cstarter.language import t

_CONSOLE = re.compile(r"\b(?:w|_t)?main\s*\(")
_WINDOWS = re.compile(r"\b(?:w|_t)?WinMain\s*\(")
_DLL_MAIN = re.compile(r"\bDllMain\s*\(")
_DLL_EXPORT = re.compile(r"__declspec\s*\(\s*dllexport\s*\)")
_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*[<"]([^>"]+)[>"]', re.MULTILINE)
_UNTRANSLATED = (".ixx", ".asm")
_PCH = (("pch.h", "pch.cpp"), ("stdafx.h", "stdafx.cpp"))


def detect(folder: Path, execute: bool = False) -> config.Detection | None:
    """Les targets proposés pour folder, ou None s'il n'a aucune source compilée. Rien ici
    n'exécute le code du projet : execute ne sert pas."""
    files = sorted(config.walk(folder, "."))
    sources = [f for f in files if f.lower().endswith(config.COMPILED)]
    if not sources:
        return None
    notes = [t(
        f"{f} : non traduit",
        f"{f}: not translated",
    ) for f in files if f.lower().endswith(_UNTRANSLATED)]
    tops = sorted({f.split("/")[0] if "/" in f else "." for f in sources})
    groups = tops if len(tops) > 1 and "." not in tops else ["."]
    texts: dict[str, dict[str, str]] = {}
    targets = [_target(folder, group, files, notes, texts) for group in groups]
    links = _links(folder, targets, texts, notes)
    solution = config.Solution(
        platforms=["x64"],
        startup_target=None,
        sln_output=".",
        global_defines={},
        targets=[config.SolutionTarget(name=target.name, depends_on=links[target.name]) for target in targets],
    )
    return config.Detection(targets=targets, notes=notes, solution=solution)


def _target(folder: Path, group: str, files: list[str], notes: list[str], all_texts: dict[str, dict[str, str]]) -> config.Target:
    name = config.safe_name(folder.resolve().name if group == "." else group)
    mine = files if group == "." else [f for f in files if f.startswith(group + "/")]
    texts = {
        f: (folder / f).read_text(encoding="utf-8", errors="replace")
        for f in mine
        if f.lower().endswith(config.COMPILED + config.HEADERS)
    }
    all_texts[name] = texts
    sources = [f for f in mine if f.lower().endswith(config.COMPILED)]
    entries = [f for f in sources if any(r.search(texts[f]) for r in (_CONSOLE, _WINDOWS, _DLL_MAIN))]
    if len(entries) > 1:
        notes.append(
            t(
                f"{name} : plusieurs points d'entrée ({', '.join(entries)}), un seul target proposé",
                f"{name}: several entry points ({', '.join(entries)}), a single target proposed",
            )
        )
    if any(_WINDOWS.search(texts[f]) for f in sources):
        target = config.new_target(name, "executable", "windows")
    elif any(_CONSOLE.search(texts[f]) for f in sources):
        target = config.new_target(name, "executable")
    elif any(_DLL_MAIN.search(text) or _DLL_EXPORT.search(text) for text in texts.values()):
        target = config.new_target(name, "dynamic_lib")
    else:
        target = config.new_target(name, "static_lib")
    target.sources.dirs = [group]
    target.debugger.working_dir = group
    target.pch = _pch(mine)
    include = posixpath.normpath(posixpath.join(group, "include"))
    if any(f.startswith(include + "/") and f.lower().endswith(config.HEADERS) for f in mine):
        target.public_headers = include
    return target


def _links(
    folder: Path, targets: list[config.Target], texts: dict[str, dict[str, str]], notes: list[str]
) -> dict[str, list[config.Link]]:
    """Les liens que les #include laissent voir : un target qui inclut un header public d'une
    bibliothèque en dépend. Un lien qui fermerait un cycle est signalé, pas créé."""
    links: dict[str, list[config.Link]] = {target.name: [] for target in targets}
    libraries = [target for target in targets if target.type != "executable" and target.public_headers]
    for target in targets:
        included = {name for text in texts[target.name].values() for name in _INCLUDE.findall(text)}
        for library in libraries:
            if library is target or not any((folder / library.public_headers / name).is_file() for name in included):
                continue
            if _reaches(links, library.name, target.name):
                notes.append(
                    t(
                        f"{target.name} inclut les headers de {library.name}, qui dépend de lui : lien non créé",
                        f"{target.name} includes the headers of {library.name}, which depends on it: link not created",
                    )
                )
                continue
            links[target.name].append(config.Link(target=library.name, config_mapping={}))
    return links


def _reaches(links: dict[str, list[config.Link]], start: str, goal: str) -> bool:
    """start mène-t-il à goal par les liens ?"""
    seen, waiting = set(), [start]
    while waiting:
        name = waiting.pop()
        if name == goal:
            return True
        if name not in seen:
            seen.add(name)
            waiting += [link.target for link in links[name]]
    return False


def _pch(files: list[str]) -> config.Pch | None:
    """Un pch.h ou un stdafx.h, et le .cpp de même nom dans le même dossier."""
    by_lower = {f.lower(): f for f in files}
    for header, source in _PCH:
        for f in files:
            if posixpath.basename(f).lower() == source:
                found = by_lower.get(posixpath.join(posixpath.dirname(f), header).lower())
                if found:
                    return config.Pch(header=posixpath.basename(found), source=f)
    return None
