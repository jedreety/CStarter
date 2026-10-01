"""La correspondance de configurations de la solution.

Pour chaque configuration S de la solution : la configuration dans laquelle chaque
target se construit, ou None s'il ne se construit pas. Le .sln en est l'écriture.
"""

from cstarter.config.model import Link, Project
from cstarter.errors import ConfigError
from cstarter.language import t


def solution_configurations(project: Project) -> list[str]:
    """Les configurations de la solution : l'union de celles des targets, triée."""
    return sorted({c.name for target in project.targets.values() for c in target.configurations})


def build_matrix(project: Project) -> dict[str, dict[str, str | None]]:
    """{S: {target: configuration construite dans S, ou None}}.

    Lève ConfigError sur un cycle, des liens en désaccord, une configuration transmise
    qui manque, ou une bibliothèque statique liée avec un autre runtime.
    """
    links = {entry.name: entry.depends_on for entry in project.solution.targets}
    reached_by: dict[str, list[tuple[str, Link]]] = {name: [] for name in links}
    for consumer, dependencies in links.items():
        for link in dependencies:
            reached_by[link.target].append((consumer, link))
    runtimes = {
        target.name: {c.name: c.runtime_library for c in target.configurations}
        for target in project.targets.values()
    }
    order = _consumers_first(links)
    matrix = {}
    for s in solution_configurations(project):
        built: dict[str, str | None] = {}
        for name in order:
            wanted = {
                consumer: link.config_mapping.get(built[consumer], built[consumer])
                for consumer, link in reached_by[name]
                if built[consumer] is not None
            }
            if not wanted:
                built[name] = s if s in runtimes[name] else None
                continue
            chosen = set(wanted.values())
            if len(chosen) > 1:
                raise ConfigError(
                    t(
                        f"{s} : les liens vers {name} demandent {', '.join(sorted(chosen))}",
                        f"{s}: the links to {name} ask for {', '.join(sorted(chosen))}",
                    )
                )
            configuration = chosen.pop()
            if configuration not in runtimes[name]:
                raise ConfigError(
                    t(
                        f"{s} : {name} n'a pas la configuration {configuration} qu'un lien lui transmet",
                        f"{s}: {name} lacks configuration {configuration}, which a link passes to it",
                    )
                )
            if project.targets[name].type == "static_lib":
                for consumer in wanted:
                    theirs = runtimes[consumer][built[consumer]]
                    mine = runtimes[name][configuration]
                    if theirs != mine:
                        raise ConfigError(
                            t(
                                f"{s} : {consumer} ({built[consumer]}, runtime {theirs}) lierait "
                                f"{name} ({configuration}, runtime {mine}) : runtimes incompatibles",
                                f"{s}: {consumer} ({built[consumer]}, runtime {theirs}) would link "
                                f"{name} ({configuration}, runtime {mine}): incompatible runtimes",
                            )
                        )
            built[name] = configuration
        matrix[s] = built
    return matrix


def _consumers_first(links: dict[str, list[Link]]) -> list[str]:
    """Les targets, chaque consommateur avant ses dépendances. Un cycle est une erreur."""
    waiting = {name: 0 for name in links}
    for dependencies in links.values():
        for link in dependencies:
            waiting[link.target] += 1
    ready = sorted(name for name, count in waiting.items() if count == 0)
    order = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for link in links[name]:
            waiting[link.target] -= 1
            if waiting[link.target] == 0:
                ready.append(link.target)
    if len(order) < len(links):
        raise ConfigError(t("cycle dans depends_on : ", "cycle in depends_on: ") + ", ".join(sorted(set(links) - set(order))))
    return order
