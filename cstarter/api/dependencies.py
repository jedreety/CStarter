"""Le cache de dépendances et les dépendances des targets.

Les fonctions du cache écrivent tout de suite, dans %USERPROFILE%\\.cstarter\\ : elles
n'appartiennent à aucun projet. link_dependency et unlink_dependency modifient le projet
en mémoire : save_project les valide et les écrit, avec dependencies.lock.json.
"""

import dataclasses
import logging
import re
import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from cstarter import config
from cstarter.api.targets import find_configuration, get_vcxproj
from cstarter.errors import ConfigError, PackageError
from cstarter.language import t
from cstarter.packages import SOURCES, analyze, cache, github, gitlab, vcpkg

# Les avertissements, que la ligne de commande affiche.
_log = logging.getLogger(__name__)
# Une préversion : un de ces mots, qui ne touche aucune autre lettre (1.0.0-rc1, v2.0-beta.3).
_PRERELEASE = re.compile(r"(?<![a-z])(?:alpha|beta|rc|pre|preview|dev|snapshot|nightly)(?![a-z])", re.IGNORECASE)
_COMMIT = re.compile(r"[0-9a-f]{40}")
# Les liens de GitHub et de GitLab : une archive, puis une page du dépôt, sa racine d'abord.
_ARCHIVE = re.compile(r"/(?:-/)?archive/|/releases/download/", re.IGNORECASE)
_GITHUB_PAGE = re.compile(r"(https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?(?:[/?#].*)?", re.IGNORECASE)
_GITLAB_PAGE = re.compile(r"(https://gitlab\.com/[^?#]+?)/(?:-/.*)?(?:[?#].*)?", re.IGNORECASE)


def list_versions(location: str) -> config.Versions:
    """Ce que la source de location propose d'installer, avant tout téléchargement : les
    tags d'un dépôt GitHub ou GitLab, du plus récent au plus ancien, et ses branches ; la version
    d'un port vcpkg dans la baseline la plus récente. Une autre source n'en propose pas."""
    source = _source(location, None)
    if source.type in ("github", "gitlab"):
        tags, branches = (github if source.type == "github" else gitlab).versions(location)
        tags = sorted(tags, key=_release, reverse=True)
        latest = next((tag for tag in tags if not _PRERELEASE.search(tag)), None)
        return config.Versions(source=source.type, tags=tags, latest=latest, branches=branches)
    if source.type == "vcpkg":
        _, version = vcpkg.at_baseline(source.port or "", None)
        return config.Versions(source="vcpkg", tags=[version], latest=version, branches=[])
    return config.Versions(source=source.type, tags=[], latest=None, branches=[])


def analyze_dependency(location: str, tag: str | None = None) -> config.AnalysisReport:
    """Télécharge ou copie la source que location désigne, et l'examine sans rien compiler.

    location est un dépôt https://github.com/PROPRIÉTAIRE/DÉPÔT ou https://gitlab.com/GROUPE/PROJET,
    à un tag ; une autre URL https:// désigne une archive zip ou tar ; vcpkg:PORT, un port de vcpkg,
    tag étant sa version exacte ; conan:NOM/VERSION, un package de conan ; sinon, c'est un dossier
    local.
    """
    return analyze.analyze(_source(location, tag))


def install_dependency(
    name: str,
    version: str,
    location: str | None = None,
    tag: str | None = None,
    system: str | None = None,
    flags: Sequence[str] = (),
    platforms: Sequence[str] = (),
    runtime: str | None = None,
    requires: Sequence[str] = (),
    review: Callable[[config.AnalysisReport], str | None] | None = None,
) -> config.Dependency:
    """Installe name@version dans le cache, construite par le builder system pour platforms et
    runtime. requires nomme les entrées qu'elle attend, pour avertir.

    La source n'est téléchargée qu'une fois : l'analyse l'examine, puis le builder la
    construit. review reçoit le rapport de l'analyse et renvoie le builder choisi, ou None pour
    garder system. Sans l'un ni l'autre, c'est la suggestion de l'analyse, avec ses options. Sans
    platforms, x64 ; un header-only (builder none) n'a ni plateforme ni runtime. Les noms de
    requires, et la recette quand system est donné, sont vérifiés avant tout téléchargement.

    Sans location, ajoute platforms à l'entrée existante, avec sa recette. Une entrée
    existante n'est jamais écrasée.
    """
    if location is None:
        return cache.add_platforms(name, version, list(platforms))
    source = _source(location, tag)
    cache.check_requires(requires)
    if system is not None:
        cache.check_recipe(source.type, system, _platforms(system, platforms), runtime)
    with tempfile.TemporaryDirectory(prefix="cstarter-") as work:
        fetched = SOURCES[source.type](source, Path(work))
        report = analyze.examine(*fetched)
        chosen = (review(report) if review else None) or system or report.suggested_system
        if system is None and chosen == report.suggested_system:
            flags = [*report.suggested_flags, *flags]
        return cache.install(name, version, source, chosen, list(flags), _platforms(chosen, platforms), runtime, requires, fetched)


def install_for_project(
    project: config.Project | None,
    name: str,
    version: str,
    location: str,
    tag: str | None = None,
    commit: str | None = None,
    review: Callable[[config.AnalysisReport], tuple[str, list[str], list[str]]] | None = None,
) -> list[config.Dependency]:
    """Installe la source de location pour project, sans lui demander ni plateforme ni runtime :
    les plateformes de sa solution, et une entrée NOM_runtime par runtime de ses configurations,
    comme l'import, pour que chacune lie la sienne. Un header-only n'en fait qu'une, NOM.
    Sans projet, ceux d'un projet neuf : x64, et les runtimes des configurations par défaut.
    commit désigne une branche de GitHub ou de GitLab, là où elle en est.

    La source n'est téléchargée qu'une fois, et chaque entrée se construit sur sa copie.
    Une source CMake est configurée pour lister tous ses paramètres : review reçoit ce rapport et
    renvoie le builder, ses options et les paquets que la bibliothèque attend ; sans review,
    la suggestion de l'analyse. Chaque entrée attend, de chacun de ces paquets, l'entrée de son
    runtime, ou son header-only. Une entrée existante n'est jamais écrasée : les noms se vérifient
    avant le téléchargement, puis avant le premier build. Un build qui échoue retire les entrées
    déjà construites par cet appel."""
    targets = project.targets.values() if project else []
    runtimes = sorted({c.runtime_library for target in targets for c in target.configurations})
    runtimes = runtimes or sorted({c.runtime_library for c in config.default_configurations()})
    source = _source(location, tag, commit)
    entries: dict[str, str | None] = {f"{name}_{runtime.lower()}": runtime for runtime in runtimes}
    _check_free(entries, version)
    with tempfile.TemporaryDirectory(prefix="cstarter-") as work:
        folder, completed = SOURCES[source.type](source, Path(work))
        report = analyze.examine(folder, completed, configure=True)
        system, flags, packages = review(report) if review else (report.suggested_system, [], [])
        if system == report.suggested_system:
            flags = [*report.suggested_flags, *flags]
        if system == "none" or report.nature == "header_only":
            entries = {name: None if system == "none" else runtimes[0]}
            _check_free(entries, version)
        platforms = [] if system == "none" else list(project.solution.platforms if project else ["x64"])
        cached = {cached_name for cached_name, _ in cache.entries()}
        installed = []
        try:
            for entry, runtime in entries.items():
                copy = Path(work) / f"copy-{entry}"
                shutil.copytree(folder, copy, copy_function=shutil.copyfile)
                requires = [required for package in packages if (required := _required(package, runtime, cached)) is not None]
                installed.append(cache.install(entry, version, completed, system, flags, platforms, runtime, requires, (copy, completed)))
        except Exception:
            for dependency in installed:  # toutes les entrées, ou aucune : un nouvel essai ne bute sur rien
                cache.remove(dependency.name, dependency.version)
            raise
        return installed


def _required(package: str, runtime: str | None, cached: set[str]) -> str | None:
    """L'entrée du paquet package qu'attend une entrée de ce runtime : NOM_runtime, sinon NOM, un
    header-only. None si le cache n'a ni l'une ni l'autre."""
    if runtime is not None and f"{package}_{runtime.lower()}" in cached:
        return f"{package}_{runtime.lower()}"
    return package if package in cached else None


def get_dependency(name: str, version: str) -> config.Dependency:
    """L'entrée name@version du cache, telle que son metadata.json la décrit."""
    return cache.read(name, version)


def get_dependencies(project: config.Project) -> list[config.Dependency]:
    """Les entrées du cache que les targets du projet lient, triées par nom et version."""
    resolved = cache.resolve(project)
    return [resolved[key] for key in sorted(resolved)]


def list_all_dependencies() -> list[config.Dependency]:
    """Toutes les entrées du cache, triées par nom et version."""
    return [cache.read(name, version) for name, version in cache.entries()]


def remove_dependency(name: str, version: str, project: config.Project | None = None) -> None:
    """Supprime l'entrée du cache. Refusé si project la lie : les autres projets qui la
    lient, CStarter ne les connaît pas, et ils devront la reconstruire."""
    if project is not None:
        users = [
            f"{target.name} ({configuration})"
            for target in project.targets.values()
            for configuration, refs in sorted(target.dependencies.items())
            if any(ref.name == name and ref.version == version for ref in refs)
        ]
        if users:
            raise PackageError(
                t(
                    f"{name}@{version} est liée par {', '.join(users)} : déliez-la d'abord",
                    f"{name}@{version} is linked by {', '.join(users)}: unlink it first",
                )
            )
    cache.remove(name, version)


def link_dependency(project: config.Project, target: str, configuration: str, name: str, version: str) -> None:
    """Lie l'entrée name@version à la configuration du target, après trois vérifications :
    même runtime, toutes les plateformes de la solution, jamais deux entrées de la même source.
    Ce que les entrées attendent sans que la configuration le lie est signalé."""
    owner = get_vcxproj(project, target)
    chosen = find_configuration(owner, configuration)
    refs = owner.dependencies.get(configuration, [])
    if any(ref.name == name for ref in refs):
        raise ConfigError(t(f"{target} ({configuration}) lie déjà {name}", f"{target} ({configuration}) already links {name}"))
    linked = [cache.read_linked(project, ref.name, ref.version) for ref in [*refs, config.DependencyRef(name=name, version=version)]]
    config.check_dependencies(owner, chosen, project.solution.platforms, linked)
    owner.dependencies[configuration] = [*refs, config.DependencyRef(name=name, version=version)]
    for warning in config.unmet_requirements(owner, chosen, linked):
        _log.warning(warning)


def unlink_dependency(project: config.Project, target: str, configuration: str, name: str) -> None:
    """Retire l'entrée name de la configuration du target."""
    owner = get_vcxproj(project, target)
    refs = owner.dependencies.get(configuration, [])
    kept = [ref for ref in refs if ref.name != name]
    if len(kept) == len(refs):
        raise ConfigError(t(f"{target} ({configuration}) ne lie pas {name}", f"{target} ({configuration}) does not link {name}"))
    if kept:
        owner.dependencies[configuration] = kept
    else:
        del owner.dependencies[configuration]


def install_requirements(requirements: list[config.Requirement], targets: list[config.Target], platforms: list[str]) -> None:
    """Installe chaque dépendance de vcpkg.json ou de conanfile.txt, une entrée NOM_runtime par
    runtime des configurations des targets, et la lie à chaque configuration de ce runtime.
    Une entrée déjà dans le cache sert, si elle vient de la même source."""
    runtimes = sorted({c.runtime_library for target in targets for c in target.configurations})
    for requirement in requirements:
        base, version, source = _requirement(requirement)
        for runtime in runtimes:
            name = f"{base}_{runtime.lower()}"
            if (cache.folder(name, version) / "metadata.json").is_file():
                if _package(cache.read(name, version).source) != _package(source):
                    raise PackageError(
                        t(
                            f"{name}@{version} est déjà dans le cache, d'une autre source : installez celle-ci sous un autre nom",
                            f"{name}@{version} is already in the cache, from another source: install this one under another name",
                        )
                    )
            else:
                cache.install(name, version, source, source.type, requirement.flags, platforms, runtime)
            for target in targets:
                for c in target.configurations:
                    if c.runtime_library == runtime:
                        target.dependencies.setdefault(c.name, []).append(config.DependencyRef(name=name, version=version))
    for target in targets:
        for c in target.configurations:
            linked = [cache.read(ref.name, ref.version) for ref in target.dependencies.get(c.name, [])]
            config.check_dependencies(target, c, platforms, linked)


def _requirement(requirement: config.Requirement) -> tuple[str, str, config.DependencySource]:
    """Le nom de base, la version exacte et la source complète d'une dépendance importée. Pour vcpkg,
    sans version fixée, celle de la baseline, ou le version>= du manifeste s'il est plus récent."""
    source = requirement.source
    if source.type == "conan":
        base, _, rest = (source.ref or "").partition("/")
        version = re.split(r"[@#]", rest)[0]
    else:
        base, version = source.port or "", source.tag
        if version is None:
            baseline, version = vcpkg.at_baseline(base, source.baseline)
            if requirement.minimum and _numbers(requirement.minimum) > _numbers(version):
                version = requirement.minimum
            source = dataclasses.replace(source, tag=version, baseline=baseline)
    if not (config.NAME.fullmatch(base) and config.NAME.fullmatch(version)):
        raise PackageError(
            t(
                f"dépendance {source.type} « {source.port or source.ref} » : nom ou version inutilisable pour le cache",
                f"{source.type} dependency “{source.port or source.ref}”: name or version unusable for the cache",
            )
        )
    return base, version, source


def _package(source: config.DependencySource) -> tuple[str, str | None, str]:
    """Ce qui désigne le package d'une source vcpkg ou conan, révision de conan mise à part."""
    return source.type, source.port, (source.ref or "").split("#")[0]


def _numbers(version: str) -> tuple[int, ...]:
    """Les nombres d'une version, pour comparer 1.10 et 1.9 comme vcpkg."""
    return tuple(int(number) for number in re.findall(r"\d+", version))


def _release(tag: str) -> tuple:
    """Ce qui range tag parmi les versions : ses nombres, puis la version finale après ses préversions.
    À nombres égaux, une lettre collée au dernier nombre vient après lui (1.92.9b après 1.92.9), et un
    tag passe avant ses variantes (1.92.9b avant 1.92.9b-docking)."""
    match = _PRERELEASE.search(tag)
    if match is not None:
        return _numbers(tag[: match.start()]), 0, _numbers(tag[match.start() :]), "", 0
    last = [*re.finditer(r"\d+", tag)]
    rest = tag[last[-1].end() :] if last else ""
    letter = re.match(r"[a-z](?![a-z])", rest, re.IGNORECASE)
    suffix = letter[0].lower() if letter else ""
    return _numbers(tag), 1, (), suffix, -(len(rest) - len(suffix))


def _check_free(entries: dict[str, str | None], version: str) -> None:
    """Refuse, avant de rien construire, une entrée déjà dans le cache : elle n'est jamais écrasée."""
    taken = [f"{entry}@{version}" for entry in entries if cache.folder(entry, version).exists()]
    if taken:
        one = len(taken) == 1
        raise PackageError(
            t(
                f"{', '.join(taken)} {'est' if one else 'sont'} déjà dans le cache, et une entrée n'est jamais écrasée : "
                f"supprimez-{'la' if one else 'les'}, ou choisissez une autre version",
                f"{', '.join(taken)} {'is' if one else 'are'} already in the cache, and an entry is never overwritten: "
                f"remove {'it' if one else 'them'}, or choose another version",
            )
        )


def _platforms(system: str, platforms: Sequence[str]) -> list[str]:
    """Les plateformes demandées, par défaut x64, et aucune pour un header-only (builder none)."""
    return list(platforms) or ([] if system == "none" else ["x64"])


def _source(location: str, tag: str | None, commit: str | None = None) -> config.DependencySource:
    """La source que location désigne : un dépôt GitHub ou GitLab, à un tag ou à un commit, un port
    vcpkg, un package conan, une archive, ou un dossier local."""
    location = _repository(location.strip())
    if commit is not None and not _COMMIT.fullmatch(commit):
        raise PackageError(t(f"commit invalide : « {commit} »", f"invalid commit: “{commit}”"))
    if github.REPOSITORY.fullmatch(location):
        return config.DependencySource(type="github", url=location, tag=tag, commit=commit)
    if gitlab.REPOSITORY.fullmatch(location):
        return config.DependencySource(type="gitlab", url=location, tag=tag, commit=commit)
    if commit is not None:
        raise PackageError(
            t("seul un dépôt GitHub ou GitLab se désigne par un commit", "only a GitHub or GitLab repository can be designated by a commit")
        )
    if location.startswith("vcpkg:"):
        return config.DependencySource(type="vcpkg", port=location.removeprefix("vcpkg:"), tag=tag)
    if location.startswith("conan:"):
        return config.DependencySource(type="conan", ref=location.removeprefix("conan:"), tag=tag)
    if "://" in location:
        return config.DependencySource(type="url", url=location, tag=tag)
    return config.DependencySource(type="local", original_path=str(Path(location).resolve()), tag=tag, resolvable=False)


def _repository(location: str) -> str:
    """Le dépôt que désigne un lien de GitHub ou de GitLab copié du navigateur, vers une branche, un
    tag ou un fichier. Une archive reste une archive."""
    if _ARCHIVE.search(location):
        return location
    page = _GITHUB_PAGE.fullmatch(location) or _GITLAB_PAGE.fullmatch(location)
    return page[1] if page else location
