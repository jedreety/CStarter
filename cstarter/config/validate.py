"""La validation du modèle.

Elle lève ConfigError au premier problème. load l'appelle après chaque lecture et
save_project avant chaque écriture : aucun .cstarter/ invalide n'est utilisé ni écrit.
check_dependencies confronte ensuite chaque configuration aux entrées du cache qu'elle lie, et
unmet_requirements dit ce que ces entrées attendent sans que la configuration le lie.
"""

import math
import posixpath
import re
from pathlib import PureWindowsPath

from cstarter.config.mapping import build_matrix
from cstarter.config.model import (
    BUILD_SYSTEMS,
    C_STANDARDS,
    GENERATORS,
    IMPORTED_FROM,
    NAME,
    NATURES,
    OPTIMIZATIONS,
    PLATFORMS,
    RUNTIMES,
    SOURCE_MODES,
    SOURCE_TYPES,
    STANDARDS,
    SUBSYSTEMS,
    TARGET_TYPES,
    WARNING_LEVELS,
    Configuration,
    Define,
    Dependency,
    Project,
    Target,
)
from cstarter.errors import ConfigError
from cstarter.language import t

_VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
_CONFIGURATION = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_. -]*[A-Za-z0-9_])?")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_GUID = re.compile(r"\{[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}")
# Options libres qui doublent un champ structuré : runtime, optimisation,
# avertissements, débogage, optimisations au link, standard, defines, includes, pch.
_COMPILER_DOUBLES = re.compile(r"[/-](MDd?|MTd?|O[12dx]|W[0-4]|Wall|Z[iI7]|GL-?|Gy-?|std:.*|D.*|I.*|Y[cu].*)")
_LINKER_DOUBLES = re.compile(r"[/-](DEBUG(:.*)?|LTCG(:.*)?|SUBSYSTEM(:.*)?)", re.IGNORECASE)
# Un nom de .lib, sans dossier ni caractère que Windows ou MSBuild interprètent.
_LIB = re.compile(r"[A-Za-z0-9_.+-]+\.lib", re.IGNORECASE)


def validate(project: Project) -> None:
    """Vérifie tout le projet ; lève ConfigError au premier problème."""
    _check(NAME.fullmatch(project.name), t(f"project.json : nom invalide « {project.name} »", f"project.json: invalid name “{project.name}”"))
    _check(
        _VERSION.fullmatch(project.version),
        t(f"project.json : version semver attendue, pas « {project.version} »", f"project.json: semver version expected, not “{project.version}”"),
    )
    _one_of(project.generator, GENERATORS, "project.json, generator")
    _one_of(project.imported_from, IMPORTED_FROM, "project.json, imported_from")
    for target in project.targets.values():
        _target(target)
    for reference in project.vendored:
        _check(
            NAME.fullmatch(reference.name) and NAME.fullmatch(reference.version),
            t(
                f".cstarter/vendor/ : dossier invalide « {reference.name}/{reference.version} »",
                f".cstarter/vendor/: invalid folder “{reference.name}/{reference.version}”",
            ),
        )
    _solution(project)
    build_matrix(project)


def _solution(project: Project) -> None:
    solution = project.solution
    where = "solution.json"
    _check(solution.platforms, t(f"{where} : au moins une plateforme", f"{where}: at least one platform"))
    for platform in solution.platforms:
        _one_of(platform, PLATFORMS, f"{where}, platforms")
    _unique(solution.platforms, f"{where}, platforms")
    _path(solution.sln_output, f"{where}, sln_output", inside=True)
    _defines(solution.global_defines, f"{where}, global_defines")
    names = [entry.name for entry in solution.targets]
    _unique(names, f"{where}, targets")
    for name in names:
        _check(
            name in project.targets,
            t(f"{where} : le target {name} n'a pas de fichier targets/{name}.json", f"{where}: target {name} has no targets/{name}.json file"),
        )
    for name in project.targets:
        _check(name in names, t(f"targets/{name}.json : target absent de solution.json", f"targets/{name}.json: target missing from solution.json"))
    _check(
        solution.startup_target is None or solution.startup_target in names,
        t(
            f"{where}, startup_target : target inconnu « {solution.startup_target} »",
            f"{where}, startup_target: unknown target “{solution.startup_target}”",
        ),
    )
    for entry in solution.targets:
        consumer = project.targets[entry.name]
        _unique([link.target for link in entry.depends_on], t(f"{where}, depends_on de {entry.name}", f"{where}, depends_on of {entry.name}"))
        for link in entry.depends_on:
            _check(
                link.target in project.targets and link.target != entry.name,
                t(
                    f"{where} : {entry.name} dépend de « {link.target} », inconnu ou lui-même",
                    f"{where}: {entry.name} depends on “{link.target}”, unknown or itself",
                ),
            )
            dependency = project.targets[link.target]
            for mine, theirs in link.config_mapping.items():
                _check(
                    mine in _names(consumer.configurations) and theirs in _names(dependency.configurations),
                    t(
                        f"{where} : le lien {entry.name} vers {link.target} cite une configuration absente : {mine} vers {theirs}",
                        f"{where}: the link from {entry.name} to {link.target} names a missing configuration: {mine} to {theirs}",
                    ),
                )


def _target(target: Target) -> None:
    where = f"targets/{target.name}.json"
    _check(NAME.fullmatch(target.name), t(f"{where} : nom invalide « {target.name} »", f"{where}: invalid name “{target.name}”"))
    _one_of(target.type, TARGET_TYPES, f"{where}, type")
    _one_of(target.subsystem, SUBSYSTEMS, f"{where}, subsystem")
    _one_of(target.standard, STANDARDS, f"{where}, standard")
    if target.c_standard is not None:
        _one_of(target.c_standard, C_STANDARDS, f"{where}, c_standard")
    _path(target.vcxproj_dir, f"{where}, vcxproj_dir", inside=True)
    if target.public_headers is not None:
        _path(target.public_headers, f"{where}, public_headers")
    if target.pch is not None:
        _check(target.pch.header, t(f"{where}, pch.header : vide", f"{where}, pch.header: empty"))
        _path(target.pch.source, f"{where}, pch.source")
    sources = target.sources
    _one_of(sources.mode, SOURCE_MODES, f"{where}, sources.mode")
    for path in (*sources.dirs, *sources.files, *sources.include_dirs, *sources.exclude):
        _path(path, f"{where}, sources")
    _path(target.output.bin_dir, f"{where}, output.bin_dir", inside=True)
    _path(target.output.obj_dir, f"{where}, output.obj_dir", inside=True)
    _path(target.debugger.working_dir, f"{where}, debugger.working_dir")
    for variable in target.debugger.environment:
        _check(
            variable and "=" not in variable,
            t(f"{where}, debugger.environment : variable invalide « {variable} »", f"{where}, debugger.environment: invalid variable “{variable}”"),
        )
    if target.guid is not None:
        _check(_GUID.fullmatch(target.guid), t(f"{where}, guid : GUID invalide « {target.guid} »", f"{where}, guid: invalid GUID “{target.guid}”"))
    _check(target.configurations, t(f"{where} : au moins une configuration", f"{where}: at least one configuration"))
    _unique(_names(target.configurations), f"{where}, configurations")
    for configuration in target.configurations:
        _configuration(configuration, f"{where}, {configuration.name}")
    for name, entries in target.dependencies.items():
        _check(
            name in _names(target.configurations),
            t(f"{where}, dependencies : configuration inconnue « {name} »", f"{where}, dependencies: unknown configuration “{name}”"),
        )
        for entry in entries:
            # Le nom et la version deviennent des dossiers du cache, et des chemins des fichiers générés.
            _check(
                NAME.fullmatch(entry.name) and NAME.fullmatch(entry.version),
                t(
                    f"{where}, dependencies : entrée invalide « {entry.name}@{entry.version} »",
                    f"{where}, dependencies: invalid entry “{entry.name}@{entry.version}”",
                ),
            )
        _unique([entry.name for entry in entries], t(f"{where}, dependencies de {name}", f"{where}, dependencies of {name}"))


def _configuration(configuration: Configuration, where: str) -> None:
    _check(_CONFIGURATION.fullmatch(configuration.name), t(f"{where} : nom de configuration invalide", f"{where}: invalid configuration name"))
    _one_of(configuration.optimization, OPTIMIZATIONS, f"{where}, optimization")
    _one_of(configuration.warning_level, WARNING_LEVELS, f"{where}, warning_level")
    _one_of(configuration.runtime_library, RUNTIMES, f"{where}, runtime_library")
    _defines(configuration.defines, f"{where}, defines")
    for option in (token for option in configuration.compiler_options for token in option.split()):
        _check(
            not doubles_field(option),
            t(
                f"{where}, compiler_options : {option} double un champ structuré",
                f"{where}, compiler_options: {option} duplicates a structured field",
            ),
        )
    for option in (token for option in configuration.linker_options for token in option.split()):
        _check(
            not doubles_field(option, linker=True),
            t(f"{where}, linker_options : {option} double un champ structuré", f"{where}, linker_options: {option} duplicates a structured field"),
        )


def doubles_field(option: str, linker: bool = False) -> bool:
    """L'option libre, de compilation ou de link, double-t-elle un champ structuré ?"""
    return bool((_LINKER_DOUBLES if linker else _COMPILER_DOUBLES).fullmatch(option))


def validate_dependency(dependency: Dependency, where: str) -> None:
    """Vérifie une entrée du cache ; lève ConfigError au premier problème."""
    _check(NAME.fullmatch(dependency.name), t(f"{where} : nom invalide « {dependency.name} »", f"{where}: invalid name “{dependency.name}”"))
    _check(
        NAME.fullmatch(dependency.version),
        t(f"{where} : version invalide « {dependency.version} »", f"{where}: invalid version “{dependency.version}”"),
    )
    _one_of(dependency.nature, NATURES, f"{where}, nature")
    _one_of(dependency.source.type, SOURCE_TYPES, f"{where}, source.type")
    build = dependency.build
    _one_of(build.system, BUILD_SYSTEMS, f"{where}, build.system")
    for platform in build.platforms:
        _one_of(platform, PLATFORMS, f"{where}, build.platforms")
    _unique(build.platforms, f"{where}, build.platforms")
    if dependency.nature == "header_only":
        _check(build.runtime is None, t(f"{where}, build.runtime : absent pour un header-only", f"{where}, build.runtime: absent for a header-only"))
    else:
        _one_of(build.runtime or "", RUNTIMES, f"{where}, build.runtime")
        _check(build.platforms, t(f"{where}, build.platforms : au moins une plateforme", f"{where}, build.platforms: at least one platform"))
    for lib in dependency.libs:
        _check(_LIB.fullmatch(lib), t(f"{where}, libs : nom de .lib invalide « {lib} »", f"{where}, libs: invalid .lib name “{lib}”"))
    for name in dependency.requires:
        _check(NAME.fullmatch(name), t(f"{where}, requires : nom d'entrée invalide « {name} »", f"{where}, requires: invalid entry name “{name}”"))


def check_dependencies(target: Target, configuration: Configuration, platforms: list[str], entries: list[Dependency]) -> None:
    """Les vérifications de la liaison, pour les entrées que configuration lie : le runtime de la
    configuration, toutes les plateformes de la solution, et jamais deux entrées issues de la
    même source. Une entrée header-only n'a ni runtime ni plateforme."""
    where = f"{target.name} ({configuration.name})"
    seen: dict[str, str] = {}
    for entry in entries:
        label = f"{entry.name}@{entry.version}"
        if entry.nature != "header_only":
            _check(
                entry.build.runtime == configuration.runtime_library,
                t(
                    f"{where}, en {configuration.runtime_library}, lierait {label}, construite en "
                    f"{entry.build.runtime} : runtimes incompatibles",
                    f"{where}, in {configuration.runtime_library}, would link {label}, built in "
                    f"{entry.build.runtime}: incompatible runtimes",
                ),
            )
            missing = [platform for platform in platforms if platform not in entry.build.platforms]
            _check(
                not missing,
                t(
                    f"{where} : {label} n'a pas la plateforme {', '.join(missing)}",
                    f"{where}: {label} lacks platform {', '.join(missing)}",
                ),
            )
        origin = _origin(entry).casefold()
        if origin in seen:
            raise ConfigError(
                t(
                    f"{where} : {seen[origin]} et {label} viennent de la même source",
                    f"{where}: {seen[origin]} and {label} come from the same source",
                )
            )
        seen[origin] = label


def unmet_requirements(target: Target, configuration: Configuration, entries: list[Dependency]) -> list[str]:
    """Ce que les entrées liées par configuration attendent sans qu'elle le lie. Ce sont des
    avertissements : CStarter ne résout pas d'arbre, il ne refuse donc rien."""
    linked = {entry.name for entry in entries}
    return [
        t(
            f"{target.name} ({configuration.name}) : {entry.name}@{entry.version} attend {name}, que cette configuration ne lie pas",
            f"{target.name} ({configuration.name}): {entry.name}@{entry.version} expects {name}, which this configuration does not link",
        )
        for entry in entries
        for name in entry.requires
        if name not in linked
    ]


def _origin(entry: Dependency) -> str:
    """La bibliothèque d'où vient l'entrée, quelle que soit sa version : le dépôt, le dossier, le
    target d'un projet, le port vcpkg ou le package conan, sinon son nom."""
    source = entry.source
    if source.url or source.original_path:
        origin = source.url or source.original_path
        if source.type == "local_project":  # un projet exporte plusieurs targets
            origin += "|" + next((flag for flag in entry.build.flags if flag.startswith("target=")), "")
        return origin
    if source.port or source.ref:
        return f"{source.type}:{source.port or (source.ref or '').split('/')[0]}"
    return entry.name


def _defines(defines: dict[str, Define], where: str) -> None:
    """Les quatre formes d'un define : null, une valeur brute, un nombre, {"string": ...}."""
    for name, value in defines.items():
        _check(_IDENTIFIER.fullmatch(name), t(f"{where} : nom de define invalide « {name} »", f"{where}: invalid define name “{name}”"))
        valid = (
            value is None
            or isinstance(value, str)
            or (isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value))
            or (isinstance(value, dict) and list(value) == ["string"] and isinstance(value["string"], str))
        )
        _check(
            valid,
            t(
                f'{where} : {name} attend null, un texte, un nombre ou {{"string": ...}}',
                f'{where}: {name} expects null, a text, a number or {{"string": ...}}',
            ),
        )


def _path(path: str, where: str, inside: bool = False) -> None:
    """Un chemin de .cstarter/ : relatif, à barres obliques, dans le projet si inside."""
    _check(
        path and "\\" not in path and not path.startswith("/") and not PureWindowsPath(path).drive,
        t(
            f"{where} : chemin relatif à barres obliques attendu, pas « {path} »",
            f"{where}: relative path with forward slashes expected, not “{path}”",
        ),
    )
    _check(
        not inside or posixpath.normpath(path).split("/")[0] != "..",
        t(f"{where} : « {path} » sort du projet", f"{where}: “{path}” leaves the project"),
    )


def _unique(values: list[str], where: str) -> None:
    """Pas de doublon, à la casse près : Windows et MSBuild l'ignorent."""
    folded = [value.casefold() for value in values]
    duplicates = sorted({value for value, key in zip(values, folded) if folded.count(key) > 1})
    _check(not duplicates, t(f"{where} : en double : {', '.join(duplicates)}", f"{where}: duplicated: {', '.join(duplicates)}"))


def _names(configurations: list[Configuration]) -> list[str]:
    return [c.name for c in configurations]


def _one_of(value: str, allowed: tuple[str, ...], where: str) -> None:
    _check(
        value in allowed,
        t(f"{where} : « {value} » n'est pas parmi {', '.join(allowed)}", f"{where}: “{value}” is not among {', '.join(allowed)}"),
    )


def _check(condition: object, message: str) -> None:
    if not condition:
        raise ConfigError(message)
