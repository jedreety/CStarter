"""Les targets, leurs configurations, leurs sources et leurs sorties.

Les modifications restent en mémoire : save_project les valide et les écrit.
"""

import copy
from collections.abc import Iterable

from cstarter import config
from cstarter.errors import ConfigError
from cstarter.language import t


def create_vcxproj(name: str, type: str, subsystem: str = "console") -> config.Target:
    """Un target en mémoire, aux réglages par défaut. add_vcxproj l'ajoute au projet."""
    return config.new_target(name, type, subsystem)


def add_vcxproj(project: config.Project, target: config.Target) -> None:
    if target.name in project.targets:
        raise ConfigError(t(f"le projet a déjà un target {target.name}", f"the project already has a target {target.name}"))
    project.targets[target.name] = target
    project.solution.targets.append(config.SolutionTarget(name=target.name, depends_on=[]))


def remove_vcxproj(project: config.Project, name: str) -> None:
    """Retire le target, et du démarrage s'il l'était. Refusé tant qu'un autre en dépend."""
    get_vcxproj(project, name)
    users = [entry.name for entry in project.solution.targets if any(link.target == name for link in entry.depends_on)]
    if users:
        raise ConfigError(
            t(f"{', '.join(users)} dépend de {name} : retirez d'abord ce lien", f"{', '.join(users)} depends on {name}: remove that link first")
        )
    del project.targets[name]
    project.solution.targets = [entry for entry in project.solution.targets if entry.name != name]
    if project.solution.startup_target == name:
        project.solution.startup_target = None


def rename_vcxproj(project: config.Project, name: str, new_name: str) -> None:
    """Renomme le target : son JSON, sa place dans la solution, les liens des autres targets vers lui
    et le démarrage. Ses sorties par défaut, build/bin/<nom> et build/obj/<nom>, suivent le nouveau
    nom ; ses sources et son dossier de travail ne bougent pas. Son GUID dérive de son nom :
    il change avec lui, sauf s'il vient d'une solution importée."""
    target = get_vcxproj(project, name)
    if new_name == name:
        return
    if not config.NAME.fullmatch(new_name):
        raise ConfigError(t(f"nom de target invalide : « {new_name} »", f"invalid target name: “{new_name}”"))
    if new_name.casefold() == name.casefold():
        raise ConfigError(
            t(
                f"{name} et {new_name} ne diffèrent que par la casse, que Windows ignore",
                f"{name} and {new_name} differ only in case, which Windows ignores",
            )
        )
    if any(other.casefold() == new_name.casefold() for other in project.targets):
        raise ConfigError(t(f"le projet a déjà un target {new_name}", f"the project already has a target {new_name}"))
    old, new = config.new_target(name, target.type).output, config.new_target(new_name, target.type).output
    if target.output.bin_dir == old.bin_dir:
        target.output.bin_dir = new.bin_dir
    if target.output.obj_dir == old.obj_dir:
        target.output.obj_dir = new.obj_dir
    target.name = new_name
    project.targets = {new_name if key == name else key: value for key, value in project.targets.items()}
    for entry in project.solution.targets:
        if entry.name == name:
            entry.name = new_name
        for link in entry.depends_on:
            if link.target == name:
                link.target = new_name
    if project.solution.startup_target == name:
        project.solution.startup_target = new_name


def rename_configuration(project: config.Project, target: str, name: str, new_name: str) -> None:
    """Renomme une configuration du target, avec ses entrées liées et ses correspondances :
    chaque lien continue de construire ce qu'il construisait, d'où une correspondance explicite là
    où le nom commun des deux côtés la rendait implicite."""
    owner = get_vcxproj(project, target)
    configuration = find_configuration(owner, name)
    if new_name == name:
        return
    if any(c.name.casefold() == new_name.casefold() for c in owner.configurations if c is not configuration):
        raise ConfigError(t(f"{target} a déjà une configuration {new_name}", f"{target} already has a configuration {new_name}"))
    configuration.name = new_name
    if name in owner.dependencies:
        owner.dependencies[new_name] = owner.dependencies.pop(name)
    for link in project.solution.depends_on(target):  # les liens de ce target vers ses dépendances
        if name in link.config_mapping:
            link.config_mapping[new_name] = link.config_mapping.pop(name)
        elif any(c.name == name for c in project.targets[link.target].configurations):
            link.config_mapping[new_name] = name
    for entry in project.solution.targets:  # les liens des autres targets vers celui-ci
        consumer = project.targets[entry.name]
        for link in entry.depends_on:
            if link.target != target:
                continue
            for mine, theirs in list(link.config_mapping.items()):
                if theirs == name:
                    link.config_mapping[mine] = new_name
            if name not in link.config_mapping and any(c.name == name for c in consumer.configurations):
                link.config_mapping[name] = new_name


def get_vcxprojs(project: config.Project) -> list[config.Target]:
    return [project.targets[entry.name] for entry in project.solution.targets]


def get_vcxproj(project: config.Project, name: str) -> config.Target:
    if name not in project.targets:
        raise ConfigError(t(f"target inconnu : {name}", f"unknown target: {name}"))
    return project.targets[name]


def add_configuration(
    project: config.Project, target: str, name: str, copy_of: str | None = None
) -> config.Configuration:
    """Ajoute au target la configuration name, copie de copy_of ou de sa première : ses réglages, ses
    entrées du cache liées, et, vers chaque dépendance qui n'a pas de configuration name, la
    configuration que la copiée y construit."""
    owner = get_vcxproj(project, target)
    if any(c.name == name for c in owner.configurations):
        raise ConfigError(t(f"{target} a déjà une configuration {name}", f"{target} already has a configuration {name}"))
    source = find_configuration(owner, copy_of) if copy_of else owner.configurations[0]
    added = copy.deepcopy(source)
    added.name = name
    owner.configurations.append(added)
    if source.name in owner.dependencies:
        owner.dependencies[name] = copy.deepcopy(owner.dependencies[source.name])
    for link in project.solution.depends_on(target):
        if not any(c.name == name for c in project.targets[link.target].configurations):
            link.config_mapping[name] = link.config_mapping.get(source.name, source.name)
    return added


def remove_configuration(project: config.Project, target: str, name: str) -> None:
    """Retire la configuration, ses dépendances et les correspondances qui partent d'elle."""
    owner = get_vcxproj(project, target)
    owner.configurations.remove(find_configuration(owner, name))
    owner.dependencies.pop(name, None)
    for link in project.solution.depends_on(target):
        link.config_mapping.pop(name, None)


def add_config_define(
    project: config.Project, target: str, configuration: str, name: str, value: config.Define = None
) -> None:
    """Ajoute ou remplace un define de la configuration."""
    find_configuration(get_vcxproj(project, target), configuration).defines[name] = value


def remove_config_define(project: config.Project, target: str, configuration: str, name: str) -> None:
    defines = find_configuration(get_vcxproj(project, target), configuration).defines
    if name not in defines:
        raise ConfigError(t(f"{target} {configuration} n'a pas de define {name}", f"{target} {configuration} has no define {name}"))
    del defines[name]


def set_source_dirs(project: config.Project, target: str, dirs: Iterable[str]) -> None:
    get_vcxproj(project, target).sources.dirs = list(dirs)


def add_include_dir(project: config.Project, target: str, path: str) -> None:
    include_dirs = get_vcxproj(project, target).sources.include_dirs
    if path in include_dirs:
        raise ConfigError(t(f"{target} a déjà le dossier d'include {path}", f"{target} already has the include folder {path}"))
    include_dirs.append(path)


def set_public_headers(project: config.Project, target: str, path: str | None) -> None:
    get_vcxproj(project, target).public_headers = path


def set_vcxproj_dir(project: config.Project, target: str, path: str) -> None:
    get_vcxproj(project, target).vcxproj_dir = path


def set_pch(project: config.Project, target: str, header: str | None, source: str | None = None) -> None:
    """L'en-tête précompilé du target : le nom que ses sources incluent et le .cpp qui le
    crée. Sans header, le target n'en a plus."""
    if header is not None and source is None:
        raise ConfigError(
            t(
                f"{target} : l'en-tête précompilé {header} demande le .cpp qui le crée",
                f"{target}: precompiled header {header} needs the .cpp that creates it",
            )
        )
    get_vcxproj(project, target).pch = None if header is None else config.Pch(header=header, source=source)


def find_configuration(target: config.Target, name: str) -> config.Configuration:
    """La configuration name du target. Interne à api/, comme install_requirements et
    linked_entries : api/__init__.py ne l'expose pas."""
    for configuration in target.configurations:
        if configuration.name == name:
            return configuration
    raise ConfigError(t(f"{target.name} n'a pas de configuration {name}", f"{target.name} has no configuration {name}"))
