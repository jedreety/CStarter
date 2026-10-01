"""Les commandes : lit les arguments, appelle api/, affiche.

Chaque commande charge le projet, le modifie et le sauvegarde. N'appelle que api/. Ses textes
suivent la langue choisie. Seul __main__.py l'importe.
"""

import argparse
import dataclasses
import json
import logging
import sys
from collections.abc import Callable, Collection
from pathlib import Path

from cstarter import api
from cstarter.errors import CStarterError, ProjectNotFoundError, UnmarkedFileError
from cstarter.language import LANGUAGES, language, set_language, t


def main(argv: list[str] | None = None) -> int:
    language()  # la langue d'abord : l'aide des commandes la suit
    args = _parser().parse_args(argv)
    logging.basicConfig(format=t("attention : %(message)s", "warning: %(message)s"), level=logging.WARNING)  # les avertissements d'api/
    try:
        code = args.run(args)
    except (CStarterError, OSError) as error:  # OSError : un fichier verrouillé, un disque plein
        print(t(f"erreur : {error}", f"error: {error}"), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(t("\ninterrompu", "\ninterrupted"), file=sys.stderr)
        return 130
    return code or 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cstarter",
        description=t("Gestionnaire de projets C et C++ pour Windows.", "C and C++ project manager for Windows."),
    )
    parser.add_argument(
        "-p",
        "--project",
        type=Path,
        metavar=t("CHEMIN", "PATH"),
        help=t(
            "le projet ; sans lui, le premier dossier .cstarter/ en remontant depuis le dossier courant",
            "the project; without it, the first .cstarter/ folder found going up from the current folder",
        ),
    )
    commands = parser.add_subparsers(metavar=t("COMMANDE", "COMMAND"), required=True)
    name, folder, target, config, version, platform = (
        t("NOM", "NAME"),
        t("DOSSIER", "FOLDER"),
        "TARGET",
        "CONFIG",
        "VERSION",
        t("PLATEFORME", "PLATFORM"),
    )

    command = commands.add_parser("create", help=t(
        "crée un projet, à partir des sources du dossier s'il y en a",
        "creates a project, from the folder's sources if any",
    ))
    command.add_argument("name", nargs="?", metavar=name, help=t(
        "nom du projet ; par défaut, celui du dossier",
        "project name; by default, the folder's",
    ))
    command.add_argument(
        "--location",
        type=Path,
        default=Path("."),
        metavar=folder,
        help=t("racine du projet ; par défaut, le dossier courant", "project root; by default, the current folder"),
    )
    command.set_defaults(run=_create)
    command = commands.add_parser(
        "detect",
        help=t(
            "importe un dossier : reconnaît sa configuration, puis écrit .cstarter/ après confirmation",
            "imports a folder: recognizes its configuration, then writes .cstarter/ after confirmation",
        ),
    )
    command.add_argument(
        "name",
        nargs="?",
        metavar=name,
        help=t(
            "nom du projet ; par défaut, celui que l'import propose, sinon celui du dossier",
            "project name; by default, the one the import proposes, else the folder's",
        ),
    )
    command.add_argument(
        "--location",
        type=Path,
        default=Path("."),
        metavar=folder,
        help=t("dossier importé ; par défaut, le dossier courant", "imported folder; by default, the current folder"),
    )
    command.set_defaults(run=_detect)
    commands.add_parser("generate", help=t("génère la solution Visual Studio", "generates the Visual Studio solution")).set_defaults(run=_generate)
    command = commands.add_parser("build", help=t("génère puis compile la solution avec MSBuild", "generates then builds the solution with MSBuild"))
    _pair_arguments(command)
    command.add_argument("--all", action="store_true", help=t(
        "chaque configuration de la solution, pour chaque plateforme",
        "every solution configuration, for every platform",
    ))
    command.set_defaults(run=_build)
    command = commands.add_parser(
        "run", help=t(
            "compile, puis lance le target de démarrage avec ses réglages de débogage",
            "builds, then runs the startup target with its debugging settings",
        )
    )
    _pair_arguments(command)
    command.set_defaults(run=_run)
    command = commands.add_parser("get-program", help=t("affiche ce que run lance", "shows what run launches"))
    _pair_arguments(command)
    command.set_defaults(run=_get_program)
    commands.add_parser("clean", help=t(
        "supprime les fichiers générés et les sorties de compilation",
        "removes generated files and build outputs",
    )).set_defaults(
        run=_clean
    )
    commands.add_parser("get-project", help=t(
        "affiche le projet et sa solution",
        "shows the project and its solution",
    )).set_defaults(run=_get_project)
    commands.add_parser("get-vcxprojs", help=t("liste les targets et leur type", "lists the targets and their type")).set_defaults(run=_get_vcxprojs)
    command = commands.add_parser("get-vcxproj", help=t("affiche la configuration d'un target", "shows a target's configuration"))
    command.add_argument("name", metavar=name)
    command.set_defaults(run=_get_vcxproj)

    command = _edit(
        commands, "add-platform", t(
            "ajoute une plateforme : x64, x86 ou ARM64",
            "adds a platform: x64, x86 or ARM64",
        ), lambda p, a: api.add_platform(p, a.platform)
    )
    command.add_argument("platform", metavar=platform)
    command = _edit(commands, "remove-platform", t("retire une plateforme", "removes a platform"), lambda p, a: api.remove_platform(p, a.platform))
    command.add_argument("platform", metavar=platform)
    command = _edit(
        commands,
        "set-startup",
        t("choisit le target de démarrage", "chooses the startup target"),
        lambda p, a: api.set_startup_target(p, a.target),
    )
    command.add_argument("target", metavar=target)
    command = _edit(
        commands,
        "set-sln-output",
        t("choisit le dossier du .sln", "chooses the .sln folder"),
        lambda p, a: api.set_sln_output(p, a.path),
    )
    command.add_argument("path", type=_slashes, metavar=folder)
    command = _edit(
        commands,
        "add-define",
        t("ajoute ou remplace un define global", "adds or replaces a global define"),
        lambda p, a: api.add_global_define(p, a.name, _value(a)),
    )
    _define_arguments(command)
    command = _edit(
        commands,
        "remove-define",
        t("retire un define global", "removes a global define"),
        lambda p, a: api.remove_global_define(p, a.name),
    )
    command.add_argument("name", metavar=name)

    command = _edit(
        commands,
        "add-target",
        t("ajoute un target, aux réglages par défaut", "adds a target, with default settings"),
        lambda p, a: api.add_vcxproj(p, api.create_vcxproj(a.name, a.type, a.subsystem)),
    )
    command.add_argument("name", metavar=name)
    command.add_argument("--type", required=True, choices=api.TARGET_TYPES)
    command.add_argument(
        "--subsystem",
        default="console",
        metavar=t("SOUS-SYSTEME", "SUBSYSTEM"),
        help=t("console ou windows ; par défaut console", "console or windows; console by default"),
    )
    command = _edit(commands, "remove-target", t("retire un target", "removes a target"), lambda p, a: api.remove_vcxproj(p, a.name))
    command.add_argument("name", metavar=name)
    command = _edit(
        commands,
        "rename-target",
        t("renomme un target, et ce qui le désigne", "renames a target, and what refers to it"),
        lambda p, a: api.rename_vcxproj(p, a.name, a.new_name),
    )
    command.add_argument("name", metavar=name)
    command.add_argument("new_name", metavar=t("NOUVEAU_NOM", "NEW_NAME"))
    command = _edit(
        commands,
        "add-config",
        t("ajoute une configuration à un target", "adds a configuration to a target"),
        lambda p, a: api.add_configuration(p, a.target, a.name, a.copy_of),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("name", metavar=name)
    command.add_argument(
        "--copy-of", metavar=config, help=t(
            "configuration copiée ; par défaut, la première du target",
            "copied configuration; by default, the target's first",
        )
    )
    command = _edit(
        commands,
        "remove-config",
        t("retire une configuration d'un target", "removes a configuration from a target"),
        lambda p, a: api.remove_configuration(p, a.target, a.name),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("name", metavar=name)
    command = _edit(
        commands,
        "rename-config",
        t("renomme une configuration d'un target, et ses correspondances", "renames a configuration of a target, and its mappings"),
        lambda p, a: api.rename_configuration(p, a.target, a.name, a.new_name),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("name", metavar=name)
    command.add_argument("new_name", metavar=t("NOUVEAU_NOM", "NEW_NAME"))
    command = _edit(
        commands,
        "add-config-define",
        t("ajoute ou remplace un define d'une configuration", "adds or replaces a define of a configuration"),
        lambda p, a: api.add_config_define(p, a.target, a.config, a.name, _value(a)),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("config", metavar=config)
    _define_arguments(command)
    command = _edit(
        commands,
        "remove-config-define",
        t("retire un define d'une configuration", "removes a define of a configuration"),
        lambda p, a: api.remove_config_define(p, a.target, a.config, a.name),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("config", metavar=config)
    command.add_argument("name", metavar=name)

    dependency = t("DEPENDANCE", "DEPENDENCY")
    command = _edit(
        commands,
        "add-project-ref",
        t("fait dépendre un target d'un autre", "makes a target depend on another"),
        lambda p, a: api.add_project_reference(p, a.target, a.dependency, _mapping(a.map)),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("dependency", metavar=dependency)
    command.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="CONFIG=CONFIG",
        help=t(
            "configuration du target et celle de la dépendance qu'elle construit",
            "configuration of the target and the dependency configuration it builds",
        ),
    )
    command = _edit(
        commands,
        "remove-project-ref",
        t("retire le lien d'un target vers un autre", "removes the link from a target to another"),
        lambda p, a: api.remove_project_reference(p, a.target, a.dependency),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("dependency", metavar=dependency)
    command = _edit(
        commands,
        "set-project-ref",
        t("remplace la correspondance de configurations d'un lien existant", "replaces the configuration mapping of an existing link"),
        lambda p, a: api.set_project_reference(p, a.target, a.dependency, _mapping(a.map)),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("dependency", metavar=dependency)
    command.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="CONFIG=CONFIG",
        help=t(
            "comme pour add-project-ref ; sans --map, chaque configuration construit la même",
            "as for add-project-ref; without --map, each configuration builds the same one",
        ),
    )

    command = _edit(
        commands,
        "set-source-dirs",
        t("remplace les dossiers de sources d'un target", "replaces the source folders of a target"),
        lambda p, a: api.set_source_dirs(p, a.target, a.dirs),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("dirs", nargs="+", type=_slashes, metavar=folder)
    command = _edit(
        commands,
        "add-include-dir",
        t("ajoute un dossier d'include à un target", "adds an include folder to a target"),
        lambda p, a: api.add_include_dir(p, a.target, a.path),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("path", type=_slashes, metavar=folder)
    command = _edit(
        commands,
        "set-public-headers",
        t("choisit le dossier des headers publics d'un target", "chooses the public headers folder of a target"),
        lambda p, a: api.set_public_headers(p, a.target, a.path),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("path", type=_slashes, metavar=folder)
    command = _edit(
        commands,
        "set-vcxproj-dir",
        t("choisit le dossier du .vcxproj d'un target", "chooses the .vcxproj folder of a target"),
        lambda p, a: api.set_vcxproj_dir(p, a.target, a.path),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("path", type=_slashes, metavar=folder)
    command = _edit(
        commands,
        "set-pch",
        t(
            "choisit l'en-tête précompilé d'un target ; sans EN-TETE, le retire",
            "chooses the precompiled header of a target; without HEADER, removes it",
        ),
        lambda p, a: api.set_pch(p, a.target, a.header, a.source),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("header", nargs="?", metavar=t(
        "EN-TETE",
        "HEADER",
    ), help=t("le nom que les sources incluent : pch.h", "the name the sources include: pch.h"))
    command.add_argument(
        "source", nargs="?", type=_slashes, metavar="SOURCE", help=t(
            "le .cpp qui le crée, relatif à la racine",
            "the .cpp that creates it, relative to the root",
        )
    )

    source_help = t(
        "dépôt https://github.com/… ou https://gitlab.com/…, archive https://…, vcpkg:PORT, conan:NOM/VERSION, ou dossier",
        "repository https://github.com/… or https://gitlab.com/…, archive https://…, vcpkg:PORT, conan:NAME/VERSION, or folder",
    )
    tag_help = t(
        "le tag d'un dépôt GitHub ou GitLab, résolu en commit ; la version exacte d'un port vcpkg",
        "the tag of a GitHub or GitLab repository, resolved to a commit; the exact version of a vcpkg port",
    )
    command = commands.add_parser("analyze-dep", help=t(
        "télécharge une dépendance et l'examine, sans rien compiler",
        "downloads a dependency and examines it, without building",
    ))
    command.add_argument("source", metavar="SOURCE", help=source_help)
    command.add_argument("--tag", metavar="TAG", help=tag_help)
    command.set_defaults(run=_analyze_dep)
    command = commands.add_parser(
        "install-dep",
        help=t(
            "installe une dépendance dans le cache, ou ajoute des plateformes à une entrée",
            "installs a dependency in the cache, or adds platforms to an entry",
        ),
    )
    command.add_argument("name", metavar=name)
    command.add_argument("version", metavar=version)
    command.add_argument(
        "source",
        nargs="?",
        metavar="SOURCE",
        help=t(
            "comme pour analyze-dep ; sans elle, --platform s'ajoute à l'entrée existante",
            "as for analyze-dep; without it, --platform is added to the existing entry",
        ),
    )
    command.add_argument("--tag", metavar="TAG", help=tag_help)
    command.add_argument(
        "--build",
        choices=api.BUILDERS,
        metavar=t("SYSTEME", "SYSTEM"),
        help=t(
            f"{', '.join(api.BUILDERS)} ; sans lui, la suggestion est proposée",
            f"{', '.join(api.BUILDERS)}; without it, the suggestion is offered",
        ),
    )
    command.add_argument(
        "--flag",
        action="append",
        default=[],
        metavar="OPTION",
        help=t(
            "option du builder, répétable : --flag=-DFMT_TEST=OFF, --flag include=DOSSIER",
            "builder option, repeatable: --flag=-DFMT_TEST=OFF, --flag include=FOLDER",
        ),
    )
    command.add_argument(
        "--platform", action="append", default=[], metavar=platform, help=t(
            "répétable ; par défaut x64, aucune pour none",
            "repeatable; x64 by default, none for none",
        )
    )
    command.add_argument("--runtime", metavar="RUNTIME", help=t("MD, MDd, MT ou MTd ; aucun pour none", "MD, MDd, MT or MTd; none for none"))
    command.add_argument(
        "--require",
        action="append",
        default=[],
        metavar=name,
        help=t(
            "entrée que celle-ci attend dans la configuration qui la lie ; répétable",
            "entry this one expects in the configuration that links it; repeatable",
        ),
    )
    command.set_defaults(run=_install_dep)
    command = _edit(
        commands,
        "link-dep",
        t("lie une entrée du cache à une configuration d'un target", "links a cache entry to a configuration of a target"),
        lambda p, a: api.link_dependency(p, a.target, a.config, a.name, a.version),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("config", metavar=config)
    command.add_argument("name", metavar=name)
    command.add_argument("version", metavar=version)
    command = _edit(
        commands,
        "unlink-dep",
        t("retire une entrée du cache d'une configuration d'un target", "removes a cache entry from a configuration of a target"),
        lambda p, a: api.unlink_dependency(p, a.target, a.config, a.name),
    )
    command.add_argument("target", metavar=target)
    command.add_argument("config", metavar=config)
    command.add_argument("name", metavar=name)
    commands.add_parser("list-deps", help=t("liste les entrées du cache", "lists the cache entries")).set_defaults(run=_list_deps)
    command = commands.add_parser("remove-dep", help=t(
        "supprime une entrée du cache, sauf si le projet la lie",
        "removes a cache entry, unless the project links it",
    ))
    command.add_argument("name", metavar=name)
    command.add_argument("version", metavar=version)
    command.set_defaults(run=_remove_dep)
    command = commands.add_parser("get-dependency", help=t("affiche une entrée du cache", "shows a cache entry"))
    command.add_argument("name", metavar=name)
    command.add_argument("version", metavar=version)
    command.set_defaults(run=_get_dependency)
    commands.add_parser(
        "get-dependencies", help=t("liste les entrées du cache que le projet lie", "lists the cache entries the project links")
    ).set_defaults(run=_get_dependencies)

    commands.add_parser(
        "restore",
        help=t(
            "reconstruit dans le cache les entrées liées qui y manquent, d'après dependencies.lock.json",
            "rebuilds in the cache the linked entries it lacks, from dependencies.lock.json",
        ),
    ).set_defaults(run=_restore)
    command = _edit(
        commands,
        "vendor-dep",
        t("copie une entrée du cache dans .cstarter/vendor/ du projet", "copies a cache entry into the project's .cstarter/vendor/"),
        lambda p, a: api.vendor_dependency(p, a.name, a.version),
    )
    command.add_argument("name", metavar=name)
    command.add_argument("version", metavar=version)
    command = _edit(
        commands,
        "unvendor-dep",
        t(
            "retire une entrée de .cstarter/vendor/ : le projet reprend celle du cache",
            "removes an entry from .cstarter/vendor/: the project uses the cache's again",
        ),
        lambda p, a: api.unvendor_dependency(p, a.name, a.version),
    )
    command.add_argument("name", metavar=name)
    command.add_argument("version", metavar=version)
    command = commands.add_parser("export-dep", help=t(
        "compile un target bibliothèque et en fait une entrée du cache",
        "builds a library target and makes it a cache entry",
    ))
    command.add_argument("target", metavar=target)
    command.add_argument("config", metavar=config)
    command.add_argument("name", metavar=name)
    command.add_argument("version", metavar=version)
    command.add_argument(
        "--platform", action="append", default=[], metavar=platform, help=t(
            "répétable ; par défaut, celles de la solution",
            "repeatable; by default, the solution's",
        )
    )
    command.set_defaults(run=_export_dep)

    branch, path = t("BRANCHE", "BRANCH"), t("CHEMIN", "PATH")
    commands.add_parser(
        "init",
        help=t(
            "crée un dépôt git et le configure : .gitignore, .gitattributes, pilote de fusion",
            "creates a git repository and configures it: .gitignore, .gitattributes, merge driver",
        ),
    ).set_defaults(run=_init)
    command = commands.add_parser(
        "clone", help=t(
            "clone un projet, puis le configure : pilote de fusion, restore, génération",
            "clones a project, then configures it: merge driver, restore, generation",
        )
    )
    command.add_argument("url", metavar="URL")
    command.add_argument(
        "location", nargs="?", type=Path, metavar=folder, help=t(
            "par défaut, le nom du dépôt dans le dossier courant",
            "by default, the repository name in the current folder",
        )
    )
    command.set_defaults(run=_clone)
    commands.add_parser("status", help=t(
        "la branche et les fichiers qui ont changé",
        "the branch and the files that changed",
    )).set_defaults(run=_status)
    command = commands.add_parser("add", help=t("prépare des fichiers pour le prochain commit", "stages files for the next commit"))
    command.add_argument("paths", nargs="+", metavar=path)
    command.set_defaults(run=_add)
    command = commands.add_parser("commit", help=t(
        "valide ce qui est préparé, ou seulement les fichiers donnés",
        "commits what is staged, or only the given files",
    ))
    command.add_argument("-m", "--message", required=True, metavar="MESSAGE")
    command.add_argument("paths", nargs="*", metavar=path)
    command.set_defaults(run=_commit)
    commands.add_parser("push", help=t("envoie la branche courante", "pushes the current branch")).set_defaults(run=_push)
    commands.add_parser(
        "pull", help=t(
            "récupère et fusionne la branche distante, puis régénère la solution",
            "fetches and merges the remote branch, then regenerates the solution",
        )
    ).set_defaults(run=_pull)
    command = commands.add_parser("branch", help=t("liste les branches, ou en crée une", "lists the branches, or creates one"))
    command.add_argument("name", nargs="?", metavar=name)
    command.set_defaults(run=_branch)
    command = commands.add_parser("switch", help=t(
        "se place sur une branche, puis régénère la solution",
        "switches to a branch, then regenerates the solution",
    ))
    command.add_argument("name", metavar=branch)
    command.add_argument("-c", "--create", action="store_true", help=t("crée la branche d'abord", "creates the branch first"))
    command.set_defaults(run=_switch)
    command = commands.add_parser(
        "merge", help=t(
            "fusionne une branche dans la courante, puis régénère la solution",
            "merges a branch into the current one, then regenerates the solution",
        )
    )
    command.add_argument("name", metavar=branch)
    command.set_defaults(run=_merge)
    command = commands.add_parser("remote", help=t(
        "liste les remotes, ou en ajoute un, ou change son adresse",
        "lists the remotes, or adds one, or changes its address",
    ))
    command.add_argument("name", nargs="?", metavar=name)
    command.add_argument("url", nargs="?", metavar="URL")
    command.set_defaults(run=_remote)
    command = commands.add_parser("log", help=t("les derniers commits de la branche courante", "the last commits of the current branch"))
    command.add_argument("-n", type=int, default=20, metavar="N", help=t("combien ; 20 par défaut", "how many; 20 by default"))
    command.set_defaults(run=_log)
    command = commands.add_parser("diff", help=t("les modifications d'un fichier depuis le dernier commit", "a file's changes since the last commit"))
    command.add_argument("path", metavar=path)
    command.set_defaults(run=_diff)
    command = commands.add_parser(
        "discard", help=t("annule les modifications de fichiers, après confirmation", "discards the changes of files, after confirmation")
    )
    command.add_argument("paths", nargs="+", metavar=path)
    command.set_defaults(run=_discard)
    commands.add_parser("update", help=t(
        "installe la dernière version publiée de CStarter",
        "installs the latest released version of CStarter",
    )).set_defaults(
        run=_update
    )
    command = commands.add_parser(
        "language", help=t("affiche la langue des messages, ou la choisit : fr ou en", "shows the language of the messages, or chooses it: fr or en")
    )
    command.add_argument("code", nargs="?", choices=LANGUAGES, metavar=t("LANGUE", "LANGUAGE"))
    command.set_defaults(run=_language)
    command = commands.add_parser("merge-driver", help=t(
        "fusionne un JSON de .cstarter/ : git la lance, init la déclare",
        "merges a .cstarter/ JSON: git runs it, init declares it",
    ))
    for argument in ("base", "ours", "theirs"):
        command.add_argument(argument, type=Path)
    command.add_argument("marker_size", type=int)
    command.add_argument("path")
    command.add_argument("ours_label")
    command.add_argument("theirs_label")
    command.set_defaults(run=_merge_driver)
    return parser


def _edit(commands, name: str, help: str, action: Callable) -> argparse.ArgumentParser:
    """Une commande qui charge le projet, le modifie par action(projet, arguments), puis le sauvegarde."""
    command = commands.add_parser(name, help=help)
    command.set_defaults(run=lambda args: _save(args, action))
    return command


def _pair_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--config", metavar=t(
        "NOM",
        "NAME",
    ), help=t("par défaut, la première configuration de la solution", "by default, the first configuration of the solution"))
    command.add_argument("--platform", metavar=t(
        "NOM",
        "NAME",
    ), help=t("par défaut, la première plateforme de la solution", "by default, the first platform of the solution"))


def _save(args: argparse.Namespace, action: Callable) -> None:
    project = api.get_project(args.project)
    action(project, args)
    _report(api.save_project(project), t("Enregistré", "Saved"), t("Rien n'a changé.", "Nothing changed."))


def _create(args: argparse.Namespace) -> None:
    """Détecte les sources, fait confirmer le type de chaque target, crée le projet, puis génère."""
    if args.project is not None:
        raise CStarterError(
            t("create désigne le dossier du projet par --location, pas par -p", "create designates the project folder with --location, not -p")
        )
    found = api.detect_sources(args.location) if args.location.is_dir() else None
    if found is not None:
        imported = api.detect(args.location)
        if imported.imported_from != "auto" or imported.pending or imported.requirements:
            print(
                t(
                    "Ce dossier a une configuration de build ou des dépendances : create ne prend que les sources, detect les importe.",
                    "This folder has a build configuration or dependencies: create takes only the sources, detect imports them.",
                )
            )
        print(t("Sources trouvées. Targets proposés :", "Sources found. Proposed targets:"))
        for target in found.targets:
            kind = f"{target.type}, {target.subsystem}" if target.type == "executable" else target.type
            links = ", ".join(link.target for link in found.solution.depends_on(target.name))
            print(
                t(f"  {target.name} ({kind}) : dossier {target.sources.dirs[0]}", f"  {target.name} ({kind}): folder {target.sources.dirs[0]}")
                + (t(f", dépend de {links}", f", depends on {links}") if links else "")
            )
        for note in found.notes:
            print(t(f"  à vérifier : {note}", f"  to check: {note}"))
        _confirm_types(found)
    project = api.create_project(args.location, args.name, found)
    print(t(f"Projet {project.name} créé dans {project.root}", f"Project {project.name} created in {project.root}"))
    _report(_confirming(lambda confirmed: api.generate(project, confirmed)), t("Écrit", "Written"), t("Rien à écrire.", "Nothing to write."))


def _detect(args: argparse.Namespace) -> None:
    """Montre ce que l'import reconnaît et ce qu'il ne traduit pas, écrit .cstarter/ après
    confirmation, puis propose de supprimer les anciens fichiers de configuration."""
    if args.project is not None:
        raise CStarterError(
            t("detect désigne le dossier importé par --location, pas par -p", "detect designates the imported folder with --location, not -p")
        )
    if (args.location / ".cstarter").exists():
        raise CStarterError(t(f"{args.location.resolve()} contient déjà un projet", f"{args.location.resolve()} already contains a project"))
    found = api.detect(args.location)
    if found is not None and found.pending:
        print(t("Lire ces fichiers exécute le code du projet :", "Reading these files runs the project's code:"))
        for item in found.pending:
            print(f"  {item}")
        if _yes(t("Les lire ? [o/N] ", "Read them? [y/N] ")):
            found = api.detect(args.location, execute=True)
    if found is not None:
        _print_detection(found)
    if found is None or not found.targets:
        raise CStarterError(t("rien à importer : aucun target reconnu", "nothing to import: no target recognized"))
    if found.imported_from == "auto":  # des sources seules : leur type n'est qu'une suggestion
        _confirm_types(found)
    if not _yes(t("Écrire .cstarter/ ? [o/N] ", "Write .cstarter/? [y/N] ")):
        raise CStarterError(t("rien n'a été écrit", "nothing was written"))
    sys.stdout.flush()  # le rapport avant la sortie des installations, même redirigée
    project = api.create_project(args.location, args.name, found)
    print(t(f"Projet {project.name} créé dans {project.root}", f"Project {project.name} created in {project.root}"))
    if found.files:
        print(t("Anciens fichiers de configuration, que .cstarter/ remplace :", "Old configuration files, which .cstarter/ replaces:"))
        for path in found.files:
            print(f"  {path}")
        if _yes(t("Les supprimer ? [o/N] ", "Remove them? [y/N] ")):
            _report(api.remove_old_files(project, found.files), t("Supprimé", "Removed"), t("Rien à supprimer.", "Nothing to remove."))
    elsewhere = project.root != Path.cwd().resolve()
    print(t(
        "La solution se génère par : cstarter ",
        "The solution is generated by: cstarter ",
    ) + (f'-p "{project.root}" ' if elsewhere else "") + "generate")


def _print_detection(found: object) -> None:
    """Ce que l'import a reconnu, ce qu'il n'a pas lu ni traduit, et ce que git montre."""
    if found.targets:
        print(t(f"Importé depuis : {found.imported_from}", f"Imported from: {found.imported_from}"))
        for target in found.targets:
            kind = f"{target.type}, {target.subsystem}" if target.type == "executable" else target.type
            links = ", ".join(link.target for link in found.solution.depends_on(target.name)) if found.solution else ""
            configurations = ", ".join(c.name for c in target.configurations)
            print(
                t(f"  {target.name} ({kind}) : {configurations}", f"  {target.name} ({kind}): {configurations}")
                + (t(f" ; dépend de {links}", f"; depends on {links}") if links else "")
            )
        print(t("Plateformes : ", "Platforms: ") + (", ".join(found.solution.platforms) if found.solution else "x64"))
    if found.requirements:
        print(
            t(
                "Dépendances à installer dans le cache, une entrée par runtime, liées à chaque target :",
                "Dependencies to install in the cache, one entry per runtime, linked to each target:",
            )
        )
        for requirement in found.requirements:
            source = requirement.source
            version = f" {source.tag}" if source.tag else f" version>= {requirement.minimum}" if requirement.minimum else ""
            print(f"  {source.type}:{source.port or source.ref}{version}")
    for item in found.pending:
        print(t(f"Non lu : {item}", f"Not read: {item}"))
    if found.notes:
        print(t("Non traduit :", "Not translated:"))
        for note in found.notes:
            print(f"  {note}")
    for item in found.info:
        print(t(f"git : {item}", f"git: {item}"))


def _generate(args: argparse.Namespace) -> None:
    project = api.get_project(args.project)
    _report(
        _confirming(lambda confirmed: api.generate(project, confirmed)),
        t("Écrit", "Written"),
        t("Rien à écrire : la solution est à jour.", "Nothing to write: the solution is up to date."),
    )


def _build(args: argparse.Namespace) -> None:
    """Une paire configuration et plateforme, ou avec --all toute la matrice, puis son bilan."""
    project = api.get_project(args.project)
    if not args.all:
        _confirming(lambda confirmed: api.build(project, args.config, args.platform, confirmed))
        return
    if args.config or args.platform:
        raise CStarterError(
            t(
                "--all compile chaque configuration et chaque plateforme : sans --config ni --platform",
                "--all builds every configuration and every platform: without --config or --platform",
            )
        )
    results = _confirming(lambda confirmed: api.build_all(project, confirmed))
    for configuration, platform, succeeded in results:
        print(t(
            f"{configuration}|{platform} : ",
            f"{configuration}|{platform}: ",
        ) + (t("réussi", "succeeded") if succeeded else t("échec", "failed")))
    failed = [result for result in results if not result[2]]
    if failed:
        raise CStarterError(
            t(
                f"compilation en échec pour {len(failed)} paire{'s' if len(failed) > 1 else ''} sur {len(results)}",
                f"build failed for {len(failed)} pair{'s' if len(failed) != 1 else ''} out of {len(results)}",
            )
        )


def _run(args: argparse.Namespace) -> int:
    """Compile, puis lance le target de démarrage ; son code de sortie devient celui de la commande."""
    project = api.get_project(args.project)
    return _confirming(lambda confirmed: api.run(project, args.config, args.platform, confirmed))


def _get_program(args: argparse.Namespace) -> None:
    program = api.get_program(api.get_project(args.project), args.config, args.platform)
    _print_json(dataclasses.asdict(program))


def _clean(args: argparse.Namespace) -> None:
    _report(api.clean(api.get_project(args.project)), t("Supprimé", "Removed"), t("Rien à supprimer.", "Nothing to remove."))


def _get_project(args: argparse.Namespace) -> None:
    """Le projet et sa solution ; get-vcxproj montre chaque target."""
    project = dataclasses.asdict(api.get_project(args.project))
    del project["targets"]
    _print_json(project)


def _get_vcxprojs(args: argparse.Namespace) -> None:
    for target in api.get_vcxprojs(api.get_project(args.project)):
        print(t(f"{target.name} : {target.type}", f"{target.name}: {target.type}"))


def _get_vcxproj(args: argparse.Namespace) -> None:
    _print_json(dataclasses.asdict(api.get_vcxproj(api.get_project(args.project), args.name)))


def _analyze_dep(args: argparse.Namespace) -> None:
    _print_report(api.analyze_dependency(args.source, args.tag))


def _install_dep(args: argparse.Namespace) -> None:
    """Sans source, ajoute des plateformes à l'entrée. Sinon montre l'analyse de la source, fait
    confirmer le système de build s'il n'est pas donné, puis installe, sans télécharger la source
    une seconde fois."""
    if args.source is None:
        if args.tag or args.build or args.flag or args.runtime or args.require:
            raise CStarterError(
                t(
                    "sans source, install-dep ne fait qu'ajouter des --platform à l'entrée, avec sa recette",
                    "without a source, install-dep only adds --platform to the entry, with its recipe",
                )
            )
        dependency = api.install_dependency(args.name, args.version, platforms=args.platform)
    else:

        def review(report: object) -> str | None:
            _print_report(report)
            system = None if args.build else _ask_build(report.suggested_system)
            sys.stdout.flush()  # le rapport avant la sortie du build, même redirigée
            return system

        dependency = api.install_dependency(
            args.name, args.version, args.source, args.tag, args.build, args.flag, args.platform, args.runtime, args.require, review
        )
    print(t(f"Installé : {_summary(dependency)}", f"Installed: {_summary(dependency)}"))


def _list_deps(args: argparse.Namespace) -> None:
    dependencies = api.list_all_dependencies()
    for dependency in dependencies:
        print(_summary(dependency))
    if not dependencies:
        print(t("Le cache est vide.", "The cache is empty."))


def _remove_dep(args: argparse.Namespace) -> None:
    """Refusé si le projet désigné, ou celui du dossier courant, lie l'entrée."""
    try:
        project = api.get_project(args.project)
    except ProjectNotFoundError:
        if args.project is not None:
            raise
        project = None
    api.remove_dependency(args.name, args.version, project)
    print(t(f"Supprimé du cache : {args.name}@{args.version}", f"Removed from the cache: {args.name}@{args.version}"))
    print(t("Un autre projet qui la lie devra la reconstruire par restore.", "Another project that links it will have to rebuild it with restore."))


def _get_dependency(args: argparse.Namespace) -> None:
    _print_json(dataclasses.asdict(api.get_dependency(args.name, args.version)))


def _get_dependencies(args: argparse.Namespace) -> None:
    dependencies = api.get_dependencies(api.get_project(args.project))
    for dependency in dependencies:
        print(_summary(dependency))
    if not dependencies:
        print(t("Le projet ne lie aucune entrée du cache.", "The project links no cache entry."))


def _restore(args: argparse.Namespace) -> None:
    _print_restore(api.restore(api.get_project(args.project)))


def _print_restore(report: object) -> None:
    """Le rapport de restore. Une entrée en échec ou à fournir fait échouer la commande."""
    for verb, keys in (
        (t("Reconstruite", "Rebuilt"), report.rebuilt),
        (t("Déjà présente", "Already present"), report.present),
        (t("Vendorée", "Vendored"), report.vendored),
    ):
        for key in keys:
            print(t(f"{verb} : {key}", f"{verb}: {key}"))
    for failure in report.failed:
        print(t(f"En échec : {failure}", f"Failed: {failure}"))
    for warning in report.warnings:
        print(t(f"À fournir : {warning}", f"To provide: {warning}"))
    if report.failed or report.warnings:
        raise CStarterError(t("restore incomplet", "incomplete restore"))
    if not (report.rebuilt or report.present or report.vendored):
        print(t("Le projet ne lie aucune entrée du cache.", "The project links no cache entry."))


def _export_dep(args: argparse.Namespace) -> None:
    project = api.get_project(args.project)
    dependency = _confirming(
        lambda confirmed: api.export_as_dependency(project, args.target, args.config, args.name, args.version, args.platform, confirmed)
    )
    print(t(f"Exporté : {_summary(dependency)}", f"Exported: {_summary(dependency)}"))


def _init(args: argparse.Namespace) -> None:
    """Propose Git LFS pour .cstarter/vendor/, puis crée le dépôt et le configure. Un
    .gitignore ou un .gitattributes existant n'est complété qu'après confirmation."""
    root = api.find_project(args.project)
    lfs = _yes(t("Suivre les binaires de .cstarter/vendor/ par Git LFS ? [o/N] ", "Track the binaries of .cstarter/vendor/ with Git LFS? [y/N] "))
    try:
        written = api.init(root, lfs)
    except UnmarkedFileError as error:
        print(
            t(
                "Ces fichiers existent : les lignes de CStarter qui leur manquent s'ajouteraient à la fin.",
                "These files exist: CStarter's missing lines would be added at the end.",
            )
        )
        for path in error.paths:
            print(f"  {path}")
        if not _yes(t("Les compléter ? [o/N] ", "Complete them? [y/N] ")):
            raise CStarterError(t("rien n'a été écrit", "nothing was written")) from None
        written = api.init(root, lfs, error.paths)
    _report(written, t("Écrit", "Written"), t(".gitignore et .gitattributes sont à jour.", ".gitignore and .gitattributes are up to date."))
    print(t("Pilote de fusion déclaré dans la configuration locale du dépôt.", "Merge driver declared in the repository's local configuration."))


def _clone(args: argparse.Namespace) -> None:
    """Clone, restore, puis génère la solution si restore n'a rien laissé à fournir."""
    if args.project is not None:
        raise CStarterError(t("clone désigne son dossier par DOSSIER, pas par -p", "clone designates its folder with FOLDER, not -p"))
    project, report = api.clone(args.url, args.location)
    print(t(f"Projet {project.name} cloné dans {project.root}", f"Project {project.name} cloned into {project.root}"))
    try:
        _print_restore(report)
    except CStarterError:
        raise CStarterError(t("restore incomplet : la solution n'a pas été générée", "incomplete restore: the solution was not generated")) from None
    _report(_confirming(lambda confirmed: api.generate(project, confirmed)), t("Écrit", "Written"), t("Rien à écrire.", "Nothing to write."))


def _status(args: argparse.Namespace) -> None:
    state = api.status(api.find_project(args.project))
    line = t(f"Sur la branche {state.branch}", f"On branch {state.branch}") if state.branch else t("HEAD détachée", "HEAD detached")
    if state.upstream:
        line += t(f", qui suit {state.upstream}", f", tracking {state.upstream}")
        if state.ahead or state.behind:
            line += t(f" : {state.ahead} commit(s) d'avance, {state.behind} de retard", f": {state.ahead} commit(s) ahead, {state.behind} behind")
    print(line)
    if state.merging:
        print(
            t(
                "Fusion en cours : cstarter commit la termine, une fois les conflits résolus.",
                "Merge in progress: cstarter commit completes it, once the conflicts are resolved.",
            )
        )
    changes = [change for change in state.changes if not change.conflicted]
    groups = (
        (t("En conflit", "In conflict"), [(change.index + change.worktree, change) for change in state.changes if change.conflicted]),
        (t("Préparés", "Staged"), [(change.index, change) for change in changes if change.index not in ".?"]),
        (t("Non préparés", "Not staged"), [(change.worktree, change) for change in changes if change.worktree not in ".?"]),
        (t("Non suivis", "Untracked"), [("?", change) for change in changes if change.index == "?"]),
    )
    for title, items in groups:
        if items:
            print(t(f"{title} :", f"{title}:"))
        for letters, change in items:
            print(f"  {letters:2} {change.path}" + (t(f", depuis {change.original}", f", from {change.original}") if change.original else ""))
    if not state.changes:
        print(t("Rien à valider.", "Nothing to commit."))


def _add(args: argparse.Namespace) -> None:
    api.add(api.find_project(args.project), [str(Path(path).resolve()) for path in args.paths])


def _commit(args: argparse.Namespace) -> None:
    api.commit(api.find_project(args.project), args.message, [str(Path(path).resolve()) for path in args.paths])


def _push(args: argparse.Namespace) -> None:
    api.push(api.find_project(args.project))


def _pull(args: argparse.Namespace) -> None:
    root = api.find_project(args.project)
    _print_git_report(_confirming(lambda confirmed: api.pull(root, confirmed)))


def _branch(args: argparse.Namespace) -> None:
    root = api.find_project(args.project)
    current = api.status(root).branch
    for name in api.branch(root, args.name):
        print(f"{'*' if name == current else ' '} {name}")


def _switch(args: argparse.Namespace) -> None:
    root = api.find_project(args.project)
    _print_git_report(_confirming(lambda confirmed: api.switch(root, args.name, args.create, confirmed)))


def _merge(args: argparse.Namespace) -> None:
    root = api.find_project(args.project)
    _print_git_report(_confirming(lambda confirmed: api.merge(root, args.name, confirmed)))


def _remote(args: argparse.Namespace) -> None:
    remotes = api.remote(api.find_project(args.project), args.name, args.url)
    for remote in remotes:
        print(f"{remote.name}  {remote.url}")
    if not remotes:
        print(t("Aucun remote.", "No remote."))


def _log(args: argparse.Namespace) -> None:
    commits = api.log(api.find_project(args.project), args.n)
    for commit in commits:
        print(f"{commit.hash[:7]}  {commit.date[:10]}  {commit.author}  {commit.subject}")
    if not commits:
        print(t("Aucun commit.", "No commit."))


def _diff(args: argparse.Namespace) -> None:
    root = api.find_project(args.project)
    print(api.diff(root, _in_repository(root, args.path)), end="")


def _discard(args: argparse.Namespace) -> None:
    """Montre les fichiers, fait confirmer, puis leur rend leur contenu du dernier commit."""
    root = api.find_project(args.project)
    paths = [_in_repository(root, path) for path in args.paths]
    print(t("Les modifications de ces fichiers seront perdues :", "The changes of these files will be lost:"))
    for path in paths:
        print(f"  {path}")
    if not _yes(t("Les annuler ? [o/N] ", "Discard them? [y/N] ")):
        raise CStarterError(t("rien n'a été annulé", "nothing was discarded"))
    _print_git_report(_confirming(lambda confirmed: api.discard(root, paths, confirmed)))


def _update(args: argparse.Namespace) -> None:
    """Télécharge la version publiée si elle est plus récente, puis lance son installeur, qui
    remplace CStarter une fois la commande finie."""
    reason = api.update_disabled()
    if reason is not None:
        raise CStarterError(reason)
    update = api.check_update()
    if update is None:
        print(t(f"CStarter {api.VERSION} est à jour.", f"CStarter {api.VERSION} is up to date."))
        return
    print(t(f"Téléchargement de CStarter {update.version}…", f"Downloading CStarter {update.version}…"))
    sys.stdout.flush()
    api.install_update(api.download_update(update))
    print(
        t(
            f"L'installeur remplace CStarter {api.VERSION} par {update.version}.",
            f"The installer replaces CStarter {api.VERSION} with {update.version}.",
        )
    )


def _language(args: argparse.Namespace) -> None:
    """La langue des messages, pour la ligne de commande comme pour l'interface."""
    if args.code is not None:
        set_language(args.code)
    print(language())


def _merge_driver(args: argparse.Namespace) -> None:
    """Ce qui reste en conflit va à git, qui l'affiche ; un conflit fait échouer la commande."""
    conflicts = api.merge_driver(args.base, args.ours, args.theirs, args.marker_size, (args.ours_label, args.theirs_label))
    for where in conflicts:
        print(t(f"conflit dans {args.path} : {where}", f"conflict in {args.path}: {where}"), file=sys.stderr)
    if conflicts:
        raise CStarterError(t(f"{args.path} : conflits laissés entre les marqueurs", f"{args.path}: conflicts left between the markers"))


def _print_git_report(report: object) -> None:
    """Ce que pull, merge, switch ou discard laisse : des conflits font échouer la commande."""
    if report.conflicts:
        print(t("En conflit :", "In conflict:"))
        for path in report.conflicts:
            print(f"  {path}")
        raise CStarterError(
            t("résolvez les conflits, puis cstarter add et cstarter commit", "resolve the conflicts, then cstarter add and cstarter commit")
        )
    if report.problem:
        print(t(f"La solution n'a pas été régénérée : {report.problem}", f"The solution was not regenerated: {report.problem}"))
    else:
        _report(report.written, t("Écrit", "Written"), t("La solution est à jour.", "The solution is up to date."))


def _print_report(report: object) -> None:
    """Le rapport d'analyse, pour que l'utilisateur choisisse le build."""
    source = report.source
    origin = source.url or source.original_path or f"{source.type}:{source.port or source.ref}"
    if source.commit:
        origin += f", tag {source.tag}, commit {source.commit}"
    if source.baseline:
        origin += f", version {source.tag}, baseline {source.baseline}"
    print(t(f"Source {source.type} : {origin}", f"{source.type} source: {origin}"))
    if source.sha256:
        print(t(f"  sha256 : {source.sha256}", f"  sha256: {source.sha256}"))
    print(t("Systèmes de build : ", "Build systems: ") + (", ".join(report.build_systems) or t("aucun", "none")))
    print(t(f"Nature probable : {report.nature}", f"Likely nature: {report.nature}"))
    if report.cmake_options:
        print(t("Options CMake :", "CMake options:"))
        for option in report.cmake_options:
            print(t(f"  {option.name} [{option.default}] : {option.description}", f"  {option.name} [{option.default}]: {option.description}"))
    if report.presets:
        print(t("Presets CMake : ", "CMake presets: ") + ", ".join(report.presets))
    print(t("Build suggéré : ", "Suggested build: ") + " ".join([report.suggested_system, *report.suggested_flags]))
    for note in report.notes:
        print(t(f"  à vérifier : {note}", f"  to check: {note}"))


def _summary(dependency: object) -> str:
    """name@version, sa nature, et pour une entrée compilée son runtime et ses plateformes."""
    build = dependency.build
    detail = dependency.nature
    if dependency.nature != "header_only":
        detail += f", {build.runtime}, {' '.join(build.platforms)}"
    return f"{dependency.name}@{dependency.version} ({detail})"


def _print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _confirming(action: Callable[[Collection[str]], object]) -> object:
    """Lance action. Si elle écraserait des fichiers sans la marque de CStarter, les montre,
    demande confirmation, puis la relance avec eux."""
    try:
        return action(())
    except UnmarkedFileError as error:
        print(t("Ces fichiers existent et n'ont pas été générés par CStarter :", "These files exist and were not generated by CStarter:"))
        for path in error.paths:
            print(f"  {path}")
        if not _yes(t("Les écraser ? [o/N] ", "Overwrite them? [y/N] ")):
            raise CStarterError(t("rien n'a été écrit", "nothing was written")) from None
        return action(error.paths)


def _confirm_types(found: object) -> None:
    """Fait confirmer le type de chaque target que proposent les sources seules. Un lien ne mène
    qu'à une bibliothèque : ceux vers un target devenu exécutable tombent."""
    for target in found.targets:
        target.type = _ask_type(target.name, target.type)
    executables = {target.name for target in found.targets if target.type == "executable"}
    for entry in found.solution.targets:
        entry.depends_on = [link for link in entry.depends_on if link.target not in executables]


def _ask_type(name: str, proposed: str) -> str:
    """Le type que l'utilisateur confirme pour le target name ; Entrée garde la proposition."""
    while True:
        answer = _ask(t(f"Type de {name} [{proposed}] : ", f"Type of {name} [{proposed}]: ")).strip()
        if not answer:
            return proposed
        if answer in api.TARGET_TYPES:
            return answer
        print(t("Types possibles : ", "Possible types: ") + ", ".join(api.TARGET_TYPES))


def _ask_build(proposed: str) -> str:
    """Le système de build que l'utilisateur confirme ; Entrée garde la suggestion."""
    while True:
        answer = _ask(t(f"Système de build [{proposed}] : ", f"Build system [{proposed}]: ")).strip()
        if not answer:
            return proposed
        if answer in api.BUILDERS:
            return answer
        print(t("Systèmes possibles : ", "Possible systems: ") + ", ".join(api.BUILDERS))


def _yes(prompt: str) -> bool:
    """L'utilisateur répond oui, dans l'une ou l'autre langue ; Entrée, ou l'entrée fermée, vaut non."""
    return _ask(prompt).strip().lower() in ("o", "oui", "y", "yes")


def _ask(prompt: str) -> str:
    """La réponse de l'utilisateur, vide si l'entrée est fermée."""
    try:
        return input(prompt)
    except EOFError:
        print()
        return ""


def _define_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("name", metavar=t("NOM", "NAME"))
    command.add_argument("value", nargs="?", metavar=t(
        "VALEUR",
        "VALUE",
    ), help=t("sans valeur, le define est seulement défini", "without a value, the define is only defined"))
    command.add_argument("--string", action="store_true", help=t(
        "VALEUR est une chaîne C, écrite entre guillemets",
        "VALUE is a C string, written between quotes",
    ))


def _value(args: argparse.Namespace) -> object:
    """La valeur d'un define : aucune, brute, ou une chaîne C avec --string."""
    if args.string:
        return {"string": args.value or ""}
    return args.value


def _slashes(path: str) -> str:
    """Un chemin de .cstarter/ tapé sous Windows : ses barres obliques inverses deviennent des
    barres obliques, la seule forme que .cstarter/ accepte."""
    return path.replace("\\", "/")


def _in_repository(root: Path, path: str) -> str:
    """Un chemin tapé, relatif au dossier courant, rendu relatif à la racine du dépôt, comme git
    status les donne."""
    repository = api.status(root).root
    try:
        return Path(path).resolve().relative_to(Path(repository).resolve()).as_posix()
    except ValueError:
        raise CStarterError(t(f"{path} est hors du dépôt", f"{path} is outside the repository")) from None


def _mapping(pairs: list[str]) -> dict[str, str]:
    mapping = {}
    for pair in pairs:
        mine, _, theirs = pair.partition("=")
        if not mine or not theirs:
            raise CStarterError(t(f"--map attend CONFIG=CONFIG, pas « {pair} »", f"--map expects CONFIG=CONFIG, not “{pair}”"))
        mapping[mine] = theirs
    return mapping


def _report(paths: list[str], verb: str, nothing: str) -> None:
    for path in paths:
        print(t(f"{verb} : {path}", f"{verb}: {path}"))
    if not paths:
        print(nothing)
