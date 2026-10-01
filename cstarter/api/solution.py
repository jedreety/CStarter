"""La solution : plateformes, target de démarrage, defines globaux, dossier du .sln et
liens entre targets.

Les modifications restent en mémoire : save_project les valide et les écrit.
"""

from cstarter import config
from cstarter.api.targets import get_vcxproj
from cstarter.errors import ConfigError
from cstarter.language import t


def set_startup_target(project: config.Project, name: str) -> None:
    get_vcxproj(project, name)
    project.solution.startup_target = name


def add_platform(project: config.Project, platform: str) -> None:
    if platform in project.solution.platforms:
        raise ConfigError(t(f"la solution a déjà la plateforme {platform}", f"the solution already has platform {platform}"))
    project.solution.platforms.append(platform)


def remove_platform(project: config.Project, platform: str) -> None:
    if platform not in project.solution.platforms:
        raise ConfigError(t(f"la solution n'a pas la plateforme {platform}", f"the solution lacks platform {platform}"))
    project.solution.platforms.remove(platform)


def add_global_define(project: config.Project, name: str, value: config.Define = None) -> None:
    """Ajoute ou remplace un define global."""
    project.solution.global_defines[name] = value


def remove_global_define(project: config.Project, name: str) -> None:
    if name not in project.solution.global_defines:
        raise ConfigError(t(f"la solution n'a pas de define global {name}", f"the solution has no global define {name}"))
    del project.solution.global_defines[name]


def set_sln_output(project: config.Project, path: str) -> None:
    project.solution.sln_output = path


def add_project_reference(
    project: config.Project, target: str, dependency: str, config_mapping: dict[str, str] | None = None
) -> None:
    """target dépend de dependency ; config_mapping traduit les configurations de l'un
    vers celles de l'autre."""
    get_vcxproj(project, target)
    get_vcxproj(project, dependency)
    links = project.solution.depends_on(target)
    if any(link.target == dependency for link in links):
        raise ConfigError(t(f"{target} dépend déjà de {dependency}", f"{target} already depends on {dependency}"))
    links.append(config.Link(target=dependency, config_mapping=dict(config_mapping or {})))


def set_project_reference(project: config.Project, target: str, dependency: str, config_mapping: dict[str, str]) -> None:
    """Remplace la correspondance de configurations du lien de target vers dependency."""
    for link in project.solution.depends_on(target):
        if link.target == dependency:
            link.config_mapping = dict(config_mapping)
            return
    raise ConfigError(t(f"{target} ne dépend pas de {dependency}", f"{target} does not depend on {dependency}"))


def remove_project_reference(project: config.Project, target: str, dependency: str) -> None:
    links = project.solution.depends_on(target)
    for link in links:
        if link.target == dependency:
            links.remove(link)
            return
    raise ConfigError(t(f"{target} ne dépend pas de {dependency}", f"{target} does not depend on {dependency}"))
