"""La portabilité : restore, le vendoring et l'export d'un target.

restore et export_as_dependency écrivent dans le cache tout de suite : il n'appartient à aucun
projet. vendor_dependency modifie le projet en mémoire : save_project copie l'entrée.
"""

import posixpath
from collections.abc import Collection, Sequence

from cstarter import config
from cstarter.api.project import generate, linked_entries
from cstarter.api.targets import find_configuration, get_vcxproj
from cstarter.errors import ConfigError, CStarterError
from cstarter.language import t
from cstarter.packages import cache


def restore(project: config.Project) -> config.RestoreReport:
    """Reconstruit ce qui manque, d'après dependencies.lock.json. Pour chaque entrée liée :
    vendorée, .cstarter/vendor/ sert ; présente dans le cache, rien à faire ; reconstructible, elle
    se reconstruit depuis le verrou, empreinte vérifiée ; sinon, l'utilisateur doit la fournir."""
    lock = config.load_lock(project.root)
    report = config.RestoreReport(rebuilt=[], present=[], vendored=[], failed=[], warnings=[])
    for name, version in linked_entries(project):
        key = f"{name}@{version}"
        if config.DependencyRef(name=name, version=version) in project.vendored:
            report.vendored.append(key)
        elif (cache.folder(name, version) / "metadata.json").is_file():
            report.present.append(key)
        elif key not in lock:
            report.warnings.append(
                t(f"{key} manque au verrou : installez-la par install-dep", f"{key} is missing from the lock: install it with install-dep")
            )
        else:
            source, build, requires = config.load_lock_entry(key, lock[key])
            if not source.resolvable:
                report.warnings.append(
                    t(
                        f"{key}, source {source.type}, ne se reconstruit pas ailleurs : "
                        "fournissez-la, ou vendorez-la depuis une machine qui l'a",
                        f"{key}, {source.type} source, cannot be rebuilt elsewhere: provide it, or vendor it from a machine that has it",
                    )
                )
                continue
            try:
                cache.install(name, version, source, build.system, build.flags, build.platforms, build.runtime, requires)
            except CStarterError as error:
                report.failed.append(t(f"{key} : {error}", f"{key}: {error}"))
            else:
                report.rebuilt.append(key)
    return report


def vendor_dependency(project: config.Project, name: str, version: str) -> None:
    """Vendore l'entrée name@version du cache : save_project la copie dans .cstarter/vendor/.
    Le projet devient autonome pour elle, qui reste dans le cache pour les autres projets."""
    reference = config.DependencyRef(name=name, version=version)
    if reference in project.vendored:
        raise ConfigError(t(f"{name}@{version} est déjà vendorée", f"{name}@{version} is already vendored"))
    cache.read(name, version)
    project.vendored = sorted([*project.vendored, reference], key=lambda ref: (ref.name, ref.version))


def unvendor_dependency(project: config.Project, name: str, version: str) -> None:
    """Rend au cache l'entrée vendorée name@version : save_project retire son dossier de
    .cstarter/vendor/. Refusé quand un target la lie et que le cache ne l'a pas : le projet
    la perdrait."""
    reference = config.DependencyRef(name=name, version=version)
    if reference not in project.vendored:
        raise ConfigError(t(f"{name}@{version} n'est pas vendorée", f"{name}@{version} is not vendored"))
    if (name, version) in linked_entries(project) and not (cache.folder(name, version) / "metadata.json").is_file():
        raise ConfigError(
            t(
                f"{name}@{version} n'est pas dans le cache : le projet la perdrait. Installez-la ou restaurez-la d'abord",
                f"{name}@{version} is not in the cache: the project would lose it. Install or restore it first",
            )
        )
    project.vendored = [ref for ref in project.vendored if ref != reference]


def export_as_dependency(
    project: config.Project,
    target: str,
    configuration: str,
    name: str,
    version: str,
    platforms: Sequence[str] = (),
    confirmed: Collection[str] = (),
) -> config.Dependency:
    """Fait du target, une bibliothèque, l'entrée name@version du cache. La solution est
    générée, puis le target compilé dans configuration pour platforms, par défaut celles de la
    solution : ses public_headers, ses .lib, ses .dll et leurs .pdb forment l'entrée. Elle reste
    figée à sa version, et sa source local_project ne se reconstruit pas ailleurs. Les entrées du
    cache que lie cette configuration deviennent ses requires : un consommateur qui ne les lie pas
    est averti.

    Comme pour generate, un fichier sans la marque de CStarter n'est écrasé que s'il figure dans
    confirmed."""
    owner = get_vcxproj(project, target)
    if owner.type == "executable":
        raise ConfigError(
            t(f"{target} est un exécutable : seule une bibliothèque s'exporte", f"{target} is an executable: only a library can be exported")
        )
    chosen = find_configuration(owner, configuration)
    platforms = list(platforms) or project.solution.platforms
    missing = [platform for platform in platforms if platform not in project.solution.platforms]
    if missing:
        raise ConfigError(t(f"la solution n'a pas la plateforme {', '.join(missing)}", f"the solution lacks platform {', '.join(missing)}"))
    # La correspondance de configurations ne vit que dans le .sln : il faut une configuration
    # de la solution qui construise le target dans celle demandée, la même de préférence.
    matrix = config.build_matrix(project)
    built_in = [s for s in sorted(matrix, key=lambda s: s != configuration) if matrix[s][target] == configuration]
    if not built_in:
        raise ConfigError(
            t(
                f"aucune configuration de la solution ne construit {target} en {configuration}",
                f"no solution configuration builds {target} in {configuration}",
            )
        )
    generate(project, confirmed)
    flags = [
        f"sln={posixpath.normpath(f'{project.solution.sln_output}/{project.name}.sln')}",
        f"target={target}",
        f"configuration={built_in[0]}",
    ]
    if owner.public_headers:
        flags.append(f"include={owner.public_headers}")
    source = config.DependencySource(type="local_project", original_path=str(project.root), resolvable=False)
    requires = [ref.name for ref in owner.dependencies.get(configuration, [])]
    return cache.install(name, version, source, "msbuild", flags, platforms, chosen.runtime_library, requires)
