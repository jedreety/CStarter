"""Le cache de dépendances : %USERPROFILE%\\.cstarter\\packages\\<nom>\\<version>\\.

Il a sa propre écriture. Une entrée se construit dans un dossier de
travail, se copie dans un dossier voisin de sa place, au nom qui commence par un point,
puis s'y renomme d'un coup. Une entrée existante n'est jamais écrasée : lui ajouter
une plateforme prépare une copie complétée, puis la substitue.
"""

import dataclasses
import os
import shutil
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import BUILDERS, SOURCES, layout, registry


def root() -> Path:
    """%USERPROFILE%\\.cstarter, celui que les fichiers générés désignent par $(USERPROFILE)."""
    profile = os.environ.get("USERPROFILE")
    if not profile:
        raise PackageError(t("variable USERPROFILE absente : le cache est introuvable", "USERPROFILE variable missing: the cache cannot be found"))
    return Path(profile) / ".cstarter"


def folder(name: str, version: str) -> Path:
    """Le dossier de l'entrée name@version. Un nom invalide n'y mène jamais hors du cache."""
    for part in (name, version):
        if not config.NAME.fullmatch(part):
            raise PackageError(t(f"nom ou version invalide : « {part} »", f"invalid name or version: “{part}”"))
    return root() / "packages" / name / version


def entries() -> list[tuple[str, str]]:
    """Les entrées du cache, (nom, version), triées. Les dossiers font foi, registry.json les suit."""
    found = sorted(
        (path.parent.parent.name, path.parent.name)
        for path in (root() / "packages").glob("*/*/metadata.json")
        if not path.parent.name.startswith(".") and not path.parent.parent.name.startswith(".")
    )
    registry.sync(root(), found)
    return found


def read(name: str, version: str, place: Path | None = None) -> config.Dependency:
    """Le metadata.json de l'entrée name@version : celle du cache, ou celle du dossier place."""
    path = (place or folder(name, version)) / "metadata.json"
    if not path.is_file():
        if place is not None:
            raise PackageError(t(f"{name}@{version} : {path} manque", f"{name}@{version}: {path} is missing"))
        raise PackageError(
            t(
                f"{name}@{version} n'est pas dans le cache : installez-la par install-dep",
                f"{name}@{version} is not in the cache: install it with install-dep",
            )
        )
    dependency = config.load_dependency(path)
    if (dependency.name, dependency.version) != (name, version):
        raise PackageError(
            t(
                f"{name}/{version}/metadata.json décrit {dependency.name}@{dependency.version}",
                f"{name}/{version}/metadata.json describes {dependency.name}@{dependency.version}",
            )
        )
    return dependency


def vendored(project: config.Project, name: str, version: str) -> Path:
    """Le dossier de l'entrée name@version dans .cstarter/vendor/ du projet."""
    return project.root / ".cstarter" / "vendor" / name / version


def read_linked(project: config.Project, name: str, version: str) -> config.Dependency:
    """L'entrée name@version telle que le projet la voit : celle de .cstarter/vendor/ si elle y est
    vendorée, sinon celle du cache."""
    return read(name, version, _vendor(project, name, version))


def resolve(project: config.Project) -> dict[tuple[str, str], config.Dependency]:
    """Les entrées que le projet lie : lues dans .cstarter/vendor/ si elles y sont, et sinon dans
    le cache. Des libs vides les désignent toutes : ce sont alors les .lib de sa
    première plateforme."""
    resolved = {}
    for target in project.targets.values():
        for references in target.dependencies.values():
            for reference in references:
                key = (reference.name, reference.version)
                if key in resolved:
                    continue
                vendor = _vendor(project, *key)
                dependency = read(*key, vendor)
                if not dependency.libs and dependency.nature != "header_only":
                    libraries = (vendor or folder(*key)) / "lib" / dependency.build.platforms[0]
                    dependency.libs = sorted(path.name for path in libraries.glob("*.lib"))
                resolved[key] = dependency
    return resolved


def vendor_files(name: str, version: str) -> dict[str, bytes]:
    """Les fichiers de l'entrée, relatifs à son dossier, pour .cstarter/vendor/. Son
    metadata.json perd le chemin d'origine : aucun chemin absolu n'entre dans un projet."""
    dependency = read(name, version)
    place = folder(name, version)
    files = {path.relative_to(place).as_posix(): path.read_bytes() for path in place.rglob("*") if path.is_file()}
    files["metadata.json"] = config.dump_dependency(
        dataclasses.replace(dependency, source=dataclasses.replace(dependency.source, original_path=None))
    )
    return files


def install(
    name: str,
    version: str,
    source: config.DependencySource,
    system: str,
    flags: list[str],
    platforms: list[str],
    runtime: str | None,
    requires: Sequence[str] = (),
    fetched: tuple[Path, config.DependencySource] | None = None,
) -> config.Dependency:
    """Récupère source, la construit par le builder system, puis l'installe en name@version
    d'un coup. Une entrée existante n'est jamais écrasée. requires nomme les
    entrées qu'elle attend. fetched, le dossier des sources et la source complétée qu'un
    appelant a déjà récupérés, évite de télécharger deux fois."""
    final = folder(name, version)
    platforms = sorted(set(platforms))
    check_recipe(source.type, system, platforms, runtime)
    check_requires(requires)
    if final.exists():
        raise PackageError(
            t(
                f"{name}@{version} est déjà dans le cache, et une entrée n'est jamais écrasée. "
                f"Pour lui ajouter une plateforme : install-dep {name} {version} --platform PLATEFORME",
                f"{name}@{version} is already in the cache, and an entry is never overwritten. "
                f"To add a platform to it: install-dep {name} {version} --platform PLATFORM",
            )
        )
    with tempfile.TemporaryDirectory(prefix="cstarter-") as work:
        sources, completed = fetched or SOURCES[source.type](source, Path(work))
        stage = Path(work) / "stage"
        stage.mkdir()
        toolset = BUILDERS[system](sources, Path(work), stage, flags, platforms, runtime)
        build = config.DependencyBuild(system=system, flags=flags, platforms=platforms, runtime=runtime, toolset=toolset)
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        dependency = _describe(name, version, stage, completed, build, list(requires), created_at)
        ready = _prepare(stage, final, dependency)
        try:
            os.rename(ready, final)
        except OSError as error:
            shutil.rmtree(ready, ignore_errors=True)
            raise PackageError(
                t(f"{name}@{version} n'a pas pu entrer dans le cache : {error}", f"{name}@{version} could not enter the cache: {error}")
            ) from None
    entries()
    return dependency


def add_platforms(name: str, version: str, platforms: list[str]) -> config.Dependency:
    """Ajoute platforms à l'entrée name@version, avec sa recette et sa source exacte (commit,
    empreinte). La copie complétée remplace l'entrée d'un coup."""
    current = read(name, version)
    build = current.build
    added = sorted(set(platforms) - set(build.platforms))
    if current.nature == "header_only":
        raise PackageError(
            t(f"{name}@{version} est un header-only : il n'a pas de plateforme", f"{name}@{version} is header-only: it has no platform")
        )
    if not added:
        if platforms:
            raise PackageError(t(f"{name}@{version} a déjà {', '.join(platforms)}", f"{name}@{version} already has {', '.join(platforms)}"))
        raise PackageError(
            t(
                f"{name}@{version} : précisez par --platform les plateformes à ajouter",
                f"{name}@{version}: give the platforms to add with --platform",
            )
        )
    check_recipe(current.source.type, build.system, added, build.runtime)
    final = folder(name, version)
    with tempfile.TemporaryDirectory(prefix="cstarter-") as work:
        sources, _ = SOURCES[current.source.type](current.source, Path(work))
        stage = Path(work) / "stage"
        shutil.copytree(final, stage, ignore=shutil.ignore_patterns("metadata.json"), copy_function=shutil.copyfile)
        fresh = Path(work) / "fresh"
        fresh.mkdir()
        BUILDERS[build.system](sources, Path(work), fresh, build.flags, added, build.runtime)
        if not layout.same_tree(fresh / "include", stage / "include"):
            raise PackageError(
                t(
                    f"{name}@{version} : les headers construits diffèrent de ceux de l'entrée",
                    f"{name}@{version}: the built headers differ from the entry's",
                )
            )
        for platform in added:
            for kind in ("lib", "bin"):
                if (fresh / kind / platform).is_dir():
                    shutil.copytree(fresh / kind / platform, stage / kind / platform, copy_function=shutil.copyfile)
        completed = dataclasses.replace(build, platforms=sorted([*build.platforms, *added]))
        dependency = _describe(name, version, stage, current.source, completed, current.requires, current.created_at)
        _swap(_prepare(stage, final, dependency), final)
    entries()
    return dependency


def remove(name: str, version: str) -> None:
    """Supprime l'entrée : renommée d'abord, elle quitte le cache d'un coup, puis s'efface."""
    final = folder(name, version)
    if not (final / "metadata.json").is_file():
        raise PackageError(t(f"{name}@{version} n'est pas dans le cache", f"{name}@{version} is not in the cache"))
    trash = _neighbour(final)
    try:
        os.rename(final, trash)
    except OSError as error:
        raise PackageError(
            t(
                f"{name}@{version} n'a pas pu être supprimée, un fichier est peut-être ouvert : {error}",
                f"{name}@{version} could not be removed, a file may be open: {error}",
            )
        ) from None
    shutil.rmtree(trash, ignore_errors=True)
    if not any(final.parent.iterdir()):
        final.parent.rmdir()
    entries()


def check_recipe(source_type: str, system: str, platforms: list[str], runtime: str | None) -> None:
    """Refuse une recette incomplète avant tout téléchargement."""
    if source_type not in SOURCES:
        raise PackageError(
            t(
                f"source {source_type} non prise en charge ; sources : {', '.join(SOURCES)}",
                f"{source_type} source not supported; sources: {', '.join(SOURCES)}",
            )
        )
    if system not in BUILDERS:
        raise PackageError(
            t(
                f"builder {system} non pris en charge ; builders : {', '.join(BUILDERS)}",
                f"{system} builder not supported; builders: {', '.join(BUILDERS)}",
            )
        )
    if "vcpkg" in (source_type, system) or "conan" in (source_type, system):
        if source_type != system:
            raise PackageError(
                t(
                    f"les sources vcpkg et conan délèguent la construction à leur builder : pas de source {source_type} avec le builder {system}",
                    f"vcpkg and conan sources delegate the build to their own builder: no {source_type} source with the {system} builder",
                )
            )
    for platform in platforms:
        if platform not in config.PLATFORMS:
            raise PackageError(
                t(
                    f"plateforme inconnue : {platform} ; plateformes : {', '.join(config.PLATFORMS)}",
                    f"unknown platform: {platform}; platforms: {', '.join(config.PLATFORMS)}",
                )
            )
    if system == "none":
        if platforms or runtime is not None:
            raise PackageError(
                t("builder none : un header-only n'a ni plateforme ni runtime", "none builder: a header-only has neither platform nor runtime")
            )
    elif not platforms or runtime not in config.RUNTIMES:
        raise PackageError(
            t(
                f"builder {system} : précisez les plateformes et le runtime, parmi {', '.join(config.RUNTIMES)}",
                f"{system} builder: give the platforms and the runtime, among {', '.join(config.RUNTIMES)}",
            )
        )


def check_requires(requires: Sequence[str]) -> None:
    """Refuse, avant tout téléchargement, un nom d'entrée invalide dans requires."""
    for required in requires:
        if not config.NAME.fullmatch(required):
            raise PackageError(t(f"requires : nom d'entrée invalide « {required} »", f"requires: invalid entry name “{required}”"))


def _describe(
    name: str,
    version: str,
    stage: Path,
    source: config.DependencySource,
    build: config.DependencyBuild,
    requires: list[str],
    created_at: str,
) -> config.Dependency:
    """L'entrée que stage contient : sa nature et ses libs se lisent dans lib/ et bin/."""
    listed = {tuple(sorted(path.name for path in (stage / "lib" / platform).glob("*.lib"))) for platform in build.platforms}
    if len(listed) > 1:
        raise PackageError(
            t(
                f"{name}@{version} : les .lib diffèrent d'une plateforme à l'autre",
                f"{name}@{version}: the .lib files differ from one platform to another",
            )
        )
    libs = list(listed.pop()) if listed else []
    if any(next((stage / "bin" / platform).glob("*.dll"), None) for platform in build.platforms):
        nature = "dynamic_lib"
    elif libs:
        nature = "static_lib"
    elif (stage / "include").is_dir():
        nature, build = "header_only", dataclasses.replace(build, runtime=None)
    else:
        raise PackageError(
            t(
                f"{name}@{version} : rien à installer, ni headers ni bibliothèques",
                f"{name}@{version}: nothing to install, neither headers nor libraries",
            )
        )
    dependency = config.Dependency(
        name=name, version=version, nature=nature, source=source, build=build, libs=libs, requires=requires, created_at=created_at
    )
    config.validate_dependency(dependency, f"{name}@{version}")
    return dependency


def _vendor(project: config.Project, name: str, version: str) -> Path | None:
    """Le dossier de l'entrée dans .cstarter/vendor/ si le projet la vendore, sinon None."""
    return vendored(project, name, version) if config.DependencyRef(name=name, version=version) in project.vendored else None


def _prepare(stage: Path, final: Path, dependency: config.Dependency) -> Path:
    """Une copie de stage et son metadata.json, dans un dossier voisin de final : sur le même
    disque, elle s'y renomme d'un coup."""
    final.parent.mkdir(parents=True, exist_ok=True)
    ready = _neighbour(final)
    try:
        shutil.copytree(stage, ready, copy_function=shutil.copyfile)
        (ready / "metadata.json").write_bytes(config.dump_dependency(dependency))
    except BaseException:
        shutil.rmtree(ready, ignore_errors=True)
        raise
    return ready


def _swap(ready: Path, final: Path) -> None:
    """Remplace l'entrée final par ready. L'ancienne est mise de côté le temps du renommage."""
    old = _neighbour(final)
    try:
        os.rename(final, old)
    except OSError as error:
        shutil.rmtree(ready, ignore_errors=True)
        raise PackageError(
            t(
                f"{final} n'a pas pu être remplacée, un fichier est peut-être ouvert : {error}",
                f"{final} could not be replaced, a file may be open: {error}",
            )
        ) from None
    try:
        os.rename(ready, final)
    except OSError as error:
        os.rename(old, final)
        shutil.rmtree(ready, ignore_errors=True)
        raise PackageError(t(f"{final} n'a pas pu être remplacée : {error}", f"{final} could not be replaced: {error}")) from None
    shutil.rmtree(old, ignore_errors=True)


def _neighbour(final: Path) -> Path:
    """Un nom libre à côté de final, qui commence par un point : les listes du cache l'ignorent."""
    path = Path(tempfile.mkdtemp(prefix=f".{final.name}-", dir=final.parent))
    path.rmdir()
    return path
