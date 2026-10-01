"""La lecture de .cstarter/ et des metadata.json du cache :
des JSON aux dataclasses.

Ici se contrôle la forme de chaque objet : champs connus, présents, du bon type JSON.
Seuls les champs qui ont un défaut peuvent manquer. Un champ inconnu est une
erreur : réécrit, il serait perdu. Les valeurs se contrôlent ensuite par validate.
"""

import json
from collections.abc import Callable
from pathlib import Path

from cstarter.config.model import (
    Configuration,
    Debugger,
    Dependency,
    DependencyBuild,
    DependencyRef,
    DependencySource,
    Link,
    Output,
    Pch,
    Project,
    Solution,
    SolutionTarget,
    Sources,
    Target,
)
from cstarter.config.validate import validate, validate_dependency
from cstarter.errors import ConfigError
from cstarter.language import t

_REQUIRED = object()  # un champ sans défaut


def load(root: Path) -> Project:
    """Lit et valide le projet dont root contient .cstarter/."""
    base = root / ".cstarter"
    project = _fields(
        _read(base, "project.json"),
        "project.json",
        {
            "name": (_str, _REQUIRED),
            "version": (_str, _REQUIRED),
            "generator": (_str, _REQUIRED),
            "imported_from": (_str, _REQUIRED),
        },
    )
    solution = Solution(
        **_fields(
            _read(base, "solution.json"),
            "solution.json",
            {
                "platforms": (_list(_str), _REQUIRED),
                "startup_target": (_optional(_str), _REQUIRED),
                "sln_output": (_str, "."),
                "global_defines": (_map(_any), _REQUIRED),
                "targets": (_list(_solution_target), _REQUIRED),
            },
        )
    )
    targets = {}
    for path in sorted((base / "targets").glob("*.json")):
        where = f"targets/{path.name}"
        target = _target(_read(base, where), where)
        if target.name != path.stem:
            raise ConfigError(
                t(
                    f"{where} : le target s'appelle « {target.name} », pas comme son fichier",
                    f"{where}: the target is named “{target.name}”, not like its file",
                )
            )
        targets[target.name] = target
    # Une dépendance est vendorée si son dossier existe.
    vendored = sorted(
        (DependencyRef(name=path.parent.name, version=path.name) for path in (base / "vendor").glob("*/*") if path.is_dir()),
        key=lambda ref: (ref.name, ref.version),
    )
    result = Project(root=root, solution=solution, targets=targets, vendored=vendored, **project)
    validate(result)
    return result


def load_lock(root: Path) -> dict[str, object]:
    """Les entrées de .cstarter/dependencies.lock.json, par name@version, vide sans verrou.
    Elles restent telles quelles : save_project conserve celles que le cache n'a pas."""
    if not (root / ".cstarter" / "dependencies.lock.json").is_file():
        return {}
    return _map(_any)(_read(root / ".cstarter", "dependencies.lock.json"), "dependencies.lock.json")


def load_lock_entry(key: str, data: object) -> tuple[DependencySource, DependencyBuild, list[str]]:
    """La source, la recette et les entrées attendues d'une entrée du verrou, de quoi la reconstruire.
    Le verrou porte resolvable au niveau de l'entrée, pas de la source."""
    where = f"dependencies.lock.json, {key}"
    values = _fields(
        data,
        where,
        {
            "nature": (_str, _REQUIRED),
            "resolvable": (_bool, _REQUIRED),
            "source": (_any, _REQUIRED),
            "build": (_dependency_build, _REQUIRED),
            "requires": (_list(_str), []),
        },
    )
    source = values["source"]
    if not isinstance(source, dict):
        raise ConfigError(t(f"{where}, source : objet JSON attendu", f"{where}, source: JSON object expected"))
    source = _dependency_source({**source, "resolvable": values["resolvable"]}, f"{where}, source")
    return source, values["build"], list(values["requires"])


def load_dependency(path: Path) -> Dependency:
    """Lit et valide le metadata.json d'une entrée du cache."""
    where = "/".join(path.parts[-3:])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as error:
        raise ConfigError(
            t(f"{where} : UTF-8 attendu, octet {error.start} illisible", f"{where}: UTF-8 expected, unreadable byte {error.start}")
        ) from None
    except json.JSONDecodeError as error:
        raise ConfigError(
            t(f"{where} : JSON invalide, ligne {error.lineno} : {error.msg}", f"{where}: invalid JSON, line {error.lineno}: {error.msg}")
        ) from None
    dependency = Dependency(
        **_fields(
            data,
            where,
            {
                "name": (_str, _REQUIRED),
                "version": (_str, _REQUIRED),
                "nature": (_str, _REQUIRED),
                "source": (_dependency_source, _REQUIRED),
                "build": (_dependency_build, _REQUIRED),
                "libs": (_list(_str), _REQUIRED),
                "requires": (_list(_str), _REQUIRED),
                "created_at": (_str, _REQUIRED),
            },
        )
    )
    validate_dependency(dependency, where)
    return dependency


def _read(base: Path, rel: str) -> object:
    try:
        return json.loads((base / rel).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ConfigError(t(f"fichier manquant : .cstarter/{rel}", f"missing file: .cstarter/{rel}")) from None
    except UnicodeDecodeError as error:
        raise ConfigError(
            t(f"{rel} : UTF-8 attendu, octet {error.start} illisible", f"{rel}: UTF-8 expected, unreadable byte {error.start}")
        ) from None
    except json.JSONDecodeError as error:
        raise ConfigError(
            t(f"{rel} : JSON invalide, ligne {error.lineno} : {error.msg}", f"{rel}: invalid JSON, line {error.lineno}: {error.msg}")
        ) from None


def _fields(data: object, where: str, spec: dict[str, tuple[Callable, object]]) -> dict:
    """Les champs de l'objet data selon spec : {clé: (lecture, défaut ou _REQUIRED)}."""
    if not isinstance(data, dict):
        raise ConfigError(t(f"{where} : objet JSON attendu", f"{where}: JSON object expected"))
    unknown = sorted(set(data) - set(spec))
    if unknown:
        raise ConfigError(t(f"{where} : champ inconnu « {unknown[0]} »", f"{where}: unknown field “{unknown[0]}”"))
    values = {}
    for key, (read, default) in spec.items():
        if key in data:
            values[key] = read(data[key], f"{where}, {key}")
        elif default is _REQUIRED:
            raise ConfigError(t(f"{where} : champ « {key} » manquant", f"{where}: missing field “{key}”"))
        else:
            values[key] = default
    return values


def _solution_target(data: object, where: str) -> SolutionTarget:
    return SolutionTarget(**_fields(data, where, {"name": (_str, _REQUIRED), "depends_on": (_list(_link), _REQUIRED)}))


def _link(data: object, where: str) -> Link:
    return Link(**_fields(data, where, {"target": (_str, _REQUIRED), "config_mapping": (_map(_str), _REQUIRED)}))


def _target(data: object, where: str) -> Target:
    values = _fields(
        data,
        where,
        {
            "name": (_str, _REQUIRED),
            "type": (_str, _REQUIRED),
            "subsystem": (_str, "console"),
            "standard": (_str, _REQUIRED),
            "c_standard": (_optional(_str), _REQUIRED),
            "vcxproj_dir": (_str, "build"),
            "public_headers": (_optional(_str), _REQUIRED),
            "pch": (_optional(_pch), _REQUIRED),
            "sources": (_sources, _REQUIRED),
            "output": (_any, {}),
            "debugger": (_debugger, _REQUIRED),
            "guid": (_optional(_str), None),
            "configurations": (_list(_configuration), _REQUIRED),
            "dependencies": (_map(_list(_dependency)), _REQUIRED),
        },
    )
    name = values["name"]
    values["output"] = Output(
        **_fields(
            values["output"],
            f"{where}, output",
            {"bin_dir": (_str, f"build/bin/{name}"), "obj_dir": (_str, f"build/obj/{name}")},
        )
    )
    return Target(**values)


def _pch(data: object, where: str) -> Pch:
    return Pch(**_fields(data, where, {"header": (_str, _REQUIRED), "source": (_str, _REQUIRED)}))


def _sources(data: object, where: str) -> Sources:
    return Sources(
        **_fields(
            data,
            where,
            {
                "mode": (_str, _REQUIRED),
                "dirs": (_list(_str), _REQUIRED),
                "files": (_list(_str), _REQUIRED),
                "include_dirs": (_list(_str), _REQUIRED),
                "exclude": (_list(_str), _REQUIRED),
            },
        )
    )


def _debugger(data: object, where: str) -> Debugger:
    return Debugger(
        **_fields(
            data,
            where,
            {"working_dir": (_str, _REQUIRED), "arguments": (_str, _REQUIRED), "environment": (_map(_str), _REQUIRED)},
        )
    )


def _configuration(data: object, where: str) -> Configuration:
    return Configuration(
        **_fields(
            data,
            where,
            {
                "name": (_str, _REQUIRED),
                "optimization": (_str, _REQUIRED),
                "warning_level": (_str, _REQUIRED),
                "runtime_library": (_str, _REQUIRED),
                "debug_info": (_bool, _REQUIRED),
                "defines": (_map(_any), _REQUIRED),
                "whole_program_opt": (_bool, _REQUIRED),
                "function_level_linking": (_bool, _REQUIRED),
                "link_time_code_gen": (_bool, _REQUIRED),
                "compiler_options": (_list(_str), _REQUIRED),
                "linker_options": (_list(_str), _REQUIRED),
            },
        )
    )


def _dependency(data: object, where: str) -> DependencyRef:
    return DependencyRef(**_fields(data, where, {"name": (_str, _REQUIRED), "version": (_str, _REQUIRED)}))


def _dependency_source(data: object, where: str) -> DependencySource:
    """Seuls type et resolvable sont toujours présents ; les autres champs dépendent du type."""
    return DependencySource(
        **_fields(
            data,
            where,
            {
                "type": (_str, _REQUIRED),
                "url": (_optional(_str), None),
                "tag": (_optional(_str), None),
                "commit": (_optional(_str), None),
                "sha256": (_optional(_str), None),
                "tree_sha256": (_optional(_str), None),
                "port": (_optional(_str), None),
                "baseline": (_optional(_str), None),
                "ref": (_optional(_str), None),
                "original_path": (_optional(_str), None),
                "resolvable": (_bool, _REQUIRED),
            },
        )
    )


def _dependency_build(data: object, where: str) -> DependencyBuild:
    return DependencyBuild(
        **_fields(
            data,
            where,
            {
                "system": (_str, _REQUIRED),
                "flags": (_list(_str), _REQUIRED),
                "platforms": (_list(_str), _REQUIRED),
                "runtime": (_optional(_str), None),
                "toolset": (_optional(_str), None),
            },
        )
    )


def _str(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(t(f"{where} : texte attendu", f"{where}: text expected"))
    return value


def _bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(t(f"{where} : true ou false attendu", f"{where}: true or false expected"))
    return value


def _any(value: object, where: str) -> object:
    return value


def _optional(read: Callable) -> Callable:
    return lambda value, where: None if value is None else read(value, where)


def _list(read: Callable) -> Callable:
    def read_list(value: object, where: str) -> list:
        if not isinstance(value, list):
            raise ConfigError(t(f"{where} : liste attendue", f"{where}: list expected"))
        return [read(item, where) for item in value]

    return read_list


def _map(read: Callable) -> Callable:
    def read_map(value: object, where: str) -> dict:
        if not isinstance(value, dict):
            raise ConfigError(t(f"{where} : objet attendu", f"{where}: object expected"))
        return {key: read(item, f"{where}, {key}") for key, item in value.items()}

    return read_map
