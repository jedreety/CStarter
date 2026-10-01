"""Le projet : création, chargement, sauvegarde, génération, compilation et
nettoyage.

La persistance est différée : les fonctions des autres modules modifient le projet
en mémoire, save_project le valide et l'écrit. create_project écrit tout de suite.
"""

import ctypes
import logging
import os
import re
import subprocess
from collections.abc import Callable, Collection
from pathlib import Path

from cstarter import config, write
from cstarter.api.dependencies import install_requirements
from cstarter.detect import DETECTORS, sources
from cstarter.errors import CStarterError, ConfigError, PackageError, ProjectNotFoundError, ToolchainError
from cstarter.generate import GENERATORS, MARK, SUFFIXES, TOOLSETS
from cstarter.language import t
from cstarter.packages import cache
from cstarter.toolchain import msbuild

_MARK = MARK.encode("utf-8")
_LOCK = ".cstarter/dependencies.lock.json"
# Les sources de départ d'un projet neuf : @NAME@ est le nom de son target, @MACRO@ ce nom
# en identifiant du préprocesseur.
_CONSOLE = """#include <iostream>

int main()
{
    std::cout << "Hello, world!\\n";
}
"""
_WINDOWED = """#include <windows.h>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
{
    MessageBoxW(nullptr, L"Hello, world!", L"@NAME@", MB_OK);
    return 0;
}
"""
_HEADER = """#pragma once

const char* greeting();
"""
_DLL_HEADER = """#pragma once

#ifdef @MACRO@_EXPORTS
#define @MACRO@_API __declspec(dllexport)
#else
#define @MACRO@_API __declspec(dllimport)
#endif

@MACRO@_API const char* greeting();
"""
_SOURCE = """#include "@NAME@.h"

const char* greeting()
{
    return "Hello, world!";
}
"""
# Les avertissements de la génération, que la ligne de commande affiche.
_log = logging.getLogger(__name__)


def detect(folder: Path, execute: bool = False) -> config.Detection | None:
    """Lance tous les détecteurs sur folder et fusionne leurs modèles partiels, ou None s'ils
    ne reconnaissent rien. Sans execute, CMake et Premake ne sont pas lancés, car ils exécutent le
    code du projet : ce qu'ils liraient attend dans pending l'accord de l'utilisateur."""
    return config.merge([found for detector in DETECTORS if (found := detector(folder, execute)) is not None])


def detect_sources(folder: Path) -> config.Detection | None:
    """Les targets que propose le détecteur de sources seules, celui de create, ou None si
    folder n'a aucune source compilée."""
    return sources.detect(folder)


def create_project(location: Path, name: str | None = None, detection: config.Detection | None = None) -> config.Project:
    """Crée le projet dont location est la racine, et écrit son .cstarter/ aussitôt.

    Sans detection, la solution est vide. Avec elle, le projet reprend ses targets, sa solution et
    son origine, et chaque dépendance de vcpkg.json ou de conanfile.txt est d'abord installée dans
    le cache puis liée. Le target de démarrage est celui de la détection, sinon le premier
    exécutable.
    """
    root = location.resolve()
    if (root / ".cstarter").exists():
        raise CStarterError(t(f"{root} contient déjà un projet", f"{root} already contains a project"))
    targets = detection.targets if detection else []
    solution = detection.solution if detection and detection.solution else None
    solution = solution or config.Solution(platforms=["x64"], startup_target=None, sln_output=".", global_defines={}, targets=[])
    listed = {entry.name for entry in solution.targets}
    solution.targets += [config.SolutionTarget(name=target.name, depends_on=[]) for target in targets if target.name not in listed]
    executables = [target.name for target in targets if target.type == "executable"]
    if solution.startup_target is None and executables:
        solution.startup_target = executables[0]
    if detection and detection.requirements:
        install_requirements(detection.requirements, targets, solution.platforms)
    project = config.Project(
        root=root,
        name=name or (detection.name if detection else None) or config.safe_name(root.name),
        version="0.1.0",
        generator="vs2022",
        imported_from=(detection.imported_from if detection else None) or ("auto" if targets else "manual"),
        solution=solution,
        targets={target.name: target for target in targets},
        vendored=[],
    )
    save_project(project)
    return project


def create_starter(root: Path, name: str, type: str, subsystem: str = "console") -> config.Project:
    """Crée dans root, un dossier absent ou vide, le projet name : un seul target, de même
    nom et de type type, et ses sources de départ dans son dossier, qui compilent aussitôt. Un
    exécutable est le target de démarrage ; une bibliothèque expose son include/, et une DLL définit
    NOM_EXPORTS pour exporter ce que son header déclare."""
    _check_name(name)
    root = _empty(root)
    target = config.new_target(name, type, subsystem)
    macro = _macro(name)
    if type == "executable":
        files = {f"{name}/src/main.cpp": _WINDOWED if subsystem == "windows" else _CONSOLE}
    else:
        target.public_headers = f"{name}/include"
        files = {f"{name}/include/{name}.h": _DLL_HEADER if type == "dynamic_lib" else _HEADER, f"{name}/src/{name}.cpp": _SOURCE}
    if type == "dynamic_lib":
        for configuration in target.configurations:
            configuration.defines[f"{macro}_EXPORTS"] = None
    project = create_project(root, name, config.Detection(targets=[target], notes=[], imported_from="manual"))
    texts = {path: text.replace("@NAME@", name).replace("@MACRO@", macro).encode("utf-8") for path, text in files.items()}
    write.write_files(root, texts, mark=None)
    return project


def create_from_template(template: Path, root: Path, name: str) -> config.Project:
    """Crée dans root, un dossier absent ou vide, le projet name en copie du projet de template :
    ses sources et son .cstarter/, sans .git ni .vs, ni les sorties de ses targets, ni les
    fichiers générés, que la génération refait. Seul le nom du projet change."""
    _check_name(name)
    model = get_project(template)
    root = _empty(root)
    if root.is_relative_to(model.root):
        raise CStarterError(t(f"{root} est dans le modèle, {model.root}", f"{root} is inside the template, {model.root}"))
    write.copy_files(root, model.root, _template_files(model))
    project = config.load(root)
    project.name = name
    save_project(project)
    return project


def _check_name(name: str) -> None:
    if not config.NAME.fullmatch(name):
        raise ConfigError(t(f"nom de projet invalide : « {name} »", f"invalid project name: “{name}”"))


def _empty(root: Path) -> Path:
    """root résolu, s'il est absent ou vide : un nouveau projet n'y écrase rien."""
    root = root.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise CStarterError(t(f"{root} existe déjà et n'est pas vide", f"{root} already exists and is not empty"))
    return root


def _macro(name: str) -> str:
    """name en identifiant du préprocesseur : MON_PROJET pour mon-projet."""
    macro = re.sub(r"\W", "_", name, flags=re.ASCII).upper()
    return f"LIB_{macro}" if macro[0].isdigit() else macro


def _template_files(project: config.Project) -> list[str]:
    """Les fichiers qu'une copie du projet reprend, relatifs à sa racine et triés : tous, sauf .git,
    .vs, les sorties de ses targets et les fichiers générés, reconnus à leur marque."""
    outputs = {os.path.normcase(project.root / path) for path in _outputs(project)}
    generated = set()
    for path in _generated(project):
        with open(project.root / path, "rb") as file:
            if _MARK in file.read(1024):  # la marque est en tête du fichier
                generated.add(path)
    found = []
    for current, dirnames, filenames in os.walk(project.root):
        dirnames[:] = [name for name in dirnames if name not in (".git", ".vs") and os.path.normcase(Path(current, name)) not in outputs]
        here = Path(current).relative_to(project.root)
        found += [(here / name).as_posix() for name in filenames if name != ".git" and (here / name).as_posix() not in generated]
    return sorted(found)


def remove_old_files(project: config.Project, paths: list[str]) -> list[str]:
    """Supprime les anciens fichiers de configuration que l'import remplace, chemins relatifs à
    la racine. Renvoie ceux qui existaient. L'appelant a la confirmation explicite de l'utilisateur."""
    return write.remove_files(project.root, paths, mark=None)


def get_project(path: Path | None = None) -> config.Project:
    """Charge le projet du premier dossier qui contient .cstarter/, en remontant depuis
    path ou, sans lui, depuis le dossier courant."""
    return config.load(find_project(path))


def find_project(path: Path | None = None) -> Path:
    """La racine du projet, trouvée comme par get_project, sans lire .cstarter/ : les commandes git
    en ont besoin même quand un conflit le rend illisible. Le cache, %USERPROFILE%\\.cstarter\\,
    n'a pas de project.json : le profil n'est pas un projet."""
    start = (path or Path.cwd()).resolve()
    for folder in (start, *start.parents):
        if (folder / ".cstarter" / "project.json").is_file():
            return folder
    raise ProjectNotFoundError(t(f"aucun projet CStarter dans {start} ni au-dessus", f"no CStarter project in {start} or above"))


def save_project(project: config.Project) -> list[str]:
    """Valide le projet, puis écrit .cstarter/ : crée et met à jour les fichiers, copie du cache
    les entrées nouvellement vendorées, supprime les fichiers des targets retirés, le dossier des
    entrées qui ne sont plus vendorées, et le verrou s'il ne décrit plus rien. Renvoie les chemins
    écrits ou supprimés."""
    config.validate(project)
    files = config.dump(project)
    lock = _lock(project)
    if lock:
        files[_LOCK] = config.dump_lock(lock)
    for reference in project.vendored:
        place = cache.vendored(project, reference.name, reference.version)
        if not place.is_dir():
            base = place.relative_to(project.root).as_posix()
            files.update({f"{base}/{rel}": content for rel, content in cache.vendor_files(reference.name, reference.version).items()})
    targets = project.root / ".cstarter" / "targets"
    removed = [f".cstarter/targets/{path.name}" for path in targets.glob("*.json")] + [_LOCK]
    removed = [rel for rel in removed if rel not in files]
    written = write.write_files(project.root, files, mark=None) + write.remove_files(project.root, removed, mark=None)
    return written + write.remove_dirs(project.root, _unvendored(project))


def _unvendored(project: config.Project) -> list[str]:
    """Les dossiers de .cstarter/vendor/ dont le projet ne vendore plus l'entrée : celui de sa
    version, ou celui de son nom quand il n'en garde aucune autre."""
    vendor = project.root / ".cstarter" / "vendor"
    kept = {(ref.name, ref.version) for ref in project.vendored}
    dropped = [path for path in vendor.glob("*/*") if path.is_dir() and (path.parent.name, path.name) not in kept]
    folders = []
    for parent in sorted({path.parent for path in dropped}):
        others = [path for path in parent.iterdir() if path not in dropped]
        folders += [parent] if not others else [path for path in dropped if path.parent == parent]
    return [folder.relative_to(project.root).as_posix() for folder in folders]


def generate(project: config.Project, confirmed: Collection[str] = ()) -> list[str]:
    """Génère la solution et écrit les fichiers qui changent. Renvoie leurs chemins.

    Un fichier existant sans la marque de CStarter n'est écrasé que s'il figure dans
    confirmed. Sinon UnmarkedFileError les nomme, et rien n'est écrit. Sont signalés d'abord le
    toolset du générateur s'il manque sur cette machine, puis les fichiers générés que plus rien ne
    produit (un target retiré, un dossier changé), supprimés, et ce que les entrées liées attendent
    sans que leur configuration le lie.
    """
    if config.load(project.root) != project:
        raise CStarterError(
            t(
                "le projet a des modifications non sauvegardées : appelez save_project d'abord",
                "the project has unsaved changes: call save_project first",
            )
        )
    toolset = TOOLSETS[project.generator]
    missing = msbuild.missing_toolset(toolset, project.solution.platforms)
    if missing:
        _log.warning(
            t(
                f"le toolset {toolset} de {project.generator} manque pour {', '.join(missing)} : MSBuild ne compilera pas cette solution",
                f"toolset {toolset} of {project.generator} is missing for {', '.join(missing)}: MSBuild will not build this solution",
            )
        )
    dependencies = cache.resolve(project)
    files = GENERATORS[project.generator](project, dependencies)
    written = write.write_files(project.root, files, _MARK, confirmed)
    produced = {os.path.normcase(path) for path in files}
    orphans = [path for path in _generated(project) if os.path.normcase(path) not in produced]
    for path in write.remove_files(project.root, orphans, _MARK):
        _log.warning(
            t(f"{path} : fichier généré que plus rien ne produit, supprimé", f"{path}: generated file that nothing produces anymore, removed")
        )
    for target in project.targets.values():
        for c in target.configurations:
            entries = [dependencies[(ref.name, ref.version)] for ref in target.dependencies.get(c.name, [])]
            for warning in config.unmet_requirements(target, c, entries):
                _log.warning(warning)
    return written


def build(
    project: config.Project,
    configuration: str | None = None,
    platform: str | None = None,
    confirmed: Collection[str] = (),
) -> None:
    """Génère la solution, puis la compile avec MSBuild. Par défaut, la première
    configuration de la solution et sa première plateforme."""
    configuration, platform = _pair(project, configuration, platform)
    generate(project, confirmed)
    code = msbuild.build(_sln(project), configuration, platform, TOOLSETS[project.generator])
    if code != 0:
        raise ToolchainError(t(f"MSBuild a échoué, code {code}", f"MSBuild failed, code {code}"))


def get_program(project: config.Project, configuration: str | None = None, platform: str | None = None) -> config.Program:
    """Ce que run lance : l'exécutable du target de démarrage, tel que la configuration de la
    solution et la plateforme le construisent, par défaut les premières, avec les réglages de son
    débogueur. Ses arguments sont découpés comme Windows les lui passera."""
    configuration, platform = _pair(project, configuration, platform)
    name = project.solution.startup_target
    if name is None:
        raise CStarterError(t("la solution n'a pas de target de démarrage", "the solution has no startup target"))
    target = project.targets[name]
    if target.type != "executable":
        raise CStarterError(t(f"{name}, le target de démarrage, n'est pas un exécutable", f"{name}, the startup target, is not an executable"))
    built = config.build_matrix(project)[configuration][name]
    if built is None:
        raise CStarterError(t(f"{name} ne se construit pas dans la configuration {configuration}", f"{name} is not built in configuration {configuration}"))
    return config.Program(
        target=name,
        path=(project.root / target.output.bin_dir / platform / built / f"{name}.exe").resolve(),
        working_dir=(project.root / target.debugger.working_dir).resolve(),
        arguments=_arguments(target.debugger.arguments),
        environment=dict(target.debugger.environment),
        windowed=target.subsystem == "windows",
    )


def run(project: config.Project, configuration: str | None = None, platform: str | None = None, confirmed: Collection[str] = ()) -> int:
    """Compile la solution comme build, puis lance le target de démarrage (get_program) dans ce
    terminal, et renvoie son code de sortie. Un programme fenêtré est lancé sans être attendu : 0."""
    build(project, configuration, platform, confirmed)
    program = get_program(project, configuration, platform)
    check_program(program)
    command = [str(program.path), *program.arguments]
    environment = {**os.environ, **program.environment}
    if program.windowed:
        subprocess.Popen(command, cwd=program.working_dir, env=environment)
        return 0
    return subprocess.run(command, cwd=program.working_dir, env=environment, check=False).returncode


def check_program(program: config.Program) -> None:
    """Refuse de lancer un programme que la compilation n'a pas produit, ou sans son dossier de travail."""
    if not program.path.is_file():
        raise CStarterError(t(f"{program.path} introuvable : la compilation ne l'a pas produit", f"{program.path} not found: the build did not produce it"))
    if not program.working_dir.is_dir():
        raise CStarterError(
            t(
                f"{program.target} : dossier de travail introuvable, {program.working_dir}",
                f"{program.target}: working folder not found, {program.working_dir}",
            )
        )


def _pair(project: config.Project, configuration: str | None, platform: str | None) -> tuple[str, str]:
    """La configuration de la solution et la plateforme demandées, par défaut les premières."""
    configurations = config.solution_configurations(project)
    if not configurations:
        raise CStarterError(t("la solution n'a aucun target à compiler", "the solution has no target to build"))
    configuration = configuration or configurations[0]
    platform = platform or project.solution.platforms[0]
    if configuration not in configurations:
        raise CStarterError(
            t(
                f"configuration « {configuration} » absente de la solution : {', '.join(configurations)}",
                f"configuration “{configuration}” is not in the solution: {', '.join(configurations)}",
            )
        )
    if platform not in project.solution.platforms:
        raise CStarterError(
            t(
                f"plateforme « {platform} » absente de la solution : {', '.join(project.solution.platforms)}",
                f"platform “{platform}” is not in the solution: {', '.join(project.solution.platforms)}",
            )
        )
    return configuration, platform


def _arguments(text: str) -> list[str]:
    """Les arguments du débogueur, une ligne de commande, découpés comme Windows les passe au
    programme : par CommandLineToArgvW, derrière un nom de programme fictif, qu'elle lit à part."""
    if not text.strip():
        return []
    shell32, kernel32 = ctypes.WinDLL("shell32"), ctypes.WinDLL("kernel32")
    shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    count = ctypes.c_int()
    argv = shell32.CommandLineToArgvW(f"x {text}", ctypes.byref(count))
    try:
        return [argv[index] for index in range(1, count.value)]
    finally:
        kernel32.LocalFree(argv)


def build_all(
    project: config.Project,
    confirmed: Collection[str] = (),
    progress: Callable[[str, str, bool], None] | None = None,
) -> list[tuple[str, str, bool]]:
    """Génère la solution, puis la compile pour chaque configuration de la solution et chaque
    plateforme. Une paire après l'autre : deux configurations de la solution peuvent
    construire un même target dans la même configuration, donc écrire les mêmes fichiers.
    MSBuild compile en parallèle les targets de chaque paire.

    Renvoie (configuration, plateforme, réussie) pour chaque paire, que progress reçoit aussi dès
    qu'elle est finie. Un échec n'arrête pas les paires suivantes, pas même une plateforme sans le
    toolset du générateur : ses paires échouent sans MSBuild, et generate l'a signalée."""
    configurations = config.solution_configurations(project)
    if not configurations:
        raise CStarterError(t("la solution n'a aucun target à compiler", "the solution has no target to build"))
    toolset = TOOLSETS[project.generator]
    missing = msbuild.missing_toolset(toolset, project.solution.platforms)
    generate(project, confirmed)
    results = []
    for configuration in configurations:
        for platform in project.solution.platforms:
            succeeded = platform not in missing and msbuild.build(_sln(project), configuration, platform, toolset) == 0
            results.append((configuration, platform, succeeded))
            if progress is not None:
                progress(configuration, platform, succeeded)
    return results


def clean(project: config.Project) -> list[str]:
    """Supprime ce que CStarter a produit : les fichiers générés, reconnus à leur marque, orphelins
    compris, et les dossiers de sorties par plateforme et configuration. Rien d'autre. Ni les
    sources ni le cache ne sont lus : clean marche aussi quand l'un d'eux manque."""
    return write.remove_files(project.root, _generated(project), _MARK) + write.remove_dirs(project.root, _outputs(project))


def _outputs(project: config.Project) -> list[str]:
    """Les dossiers de sorties de chaque target, par plateforme et configuration, relatifs à la racine."""
    return [
        f"{base}/{platform}/{c.name}"
        for target in project.targets.values()
        for base in (target.output.bin_dir, target.output.obj_dir)
        for platform in project.solution.platforms
        for c in target.configurations
    ]


def _sln(project: config.Project) -> Path:
    return project.root / project.solution.sln_output / f"{project.name}.sln"


def _generated(project: config.Project) -> list[str]:
    """Les fichiers du projet qui ont l'extension d'un fichier généré, relatifs à sa racine et triés.
    Ni les dossiers dont le nom commence par un point ni un sous-projet, qui a son propre .cstarter/,
    ne sont parcourus. write.remove_files ne supprime ensuite que ceux qui portent la marque."""
    suffixes = SUFFIXES[project.generator]
    found = []
    for current, dirnames, filenames in os.walk(project.root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".") and not Path(current, name, ".cstarter").is_dir()]
        here = Path(current).relative_to(project.root)
        found += [(here / name).as_posix() for name in filenames if name.endswith(suffixes)]
    return sorted(found)


def linked_entries(project: config.Project) -> list[tuple[str, str]]:
    """Les entrées que les targets lient, (nom, version), triées et sans doublon."""
    return sorted(
        {(ref.name, ref.version) for target in project.targets.values() for refs in target.dependencies.values() for ref in refs}
    )


def _lock(project: config.Project) -> dict[str, object]:
    """Les entrées de dependencies.lock.json : chaque name@version qu'un target lie, décrit
    par son metadata.json, celui de .cstarter/vendor/ ou celui du cache, ou repris tel quel du
    verrou quand aucun des deux ne l'a."""
    previous = config.load_lock(project.root)
    entries = {}
    for name, version in linked_entries(project):
        key = f"{name}@{version}"
        vendor = cache.vendored(project, name, version)
        if (vendor / "metadata.json").is_file():
            entries[key] = config.lock_entry(cache.read(name, version, vendor))
        elif (cache.folder(name, version) / "metadata.json").is_file():
            entries[key] = config.lock_entry(cache.read(name, version))
        elif key in previous:
            entries[key] = previous[key]
        else:
            raise PackageError(
                t(
                    f"{key} n'est ni dans le cache ni dans le verrou : installez-la par install-dep",
                    f"{key} is neither in the cache nor in the lock: install it with install-dep",
                )
            )
    return entries
