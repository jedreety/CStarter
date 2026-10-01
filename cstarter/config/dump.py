"""La sérialisation stable de .cstarter/, et des metadata.json du cache.

Ordre des clés fixe, indentation de deux espaces,
dictionnaires libres triés par clé, UTF-8 sans BOM, fin de ligne LF. Relire puis
réécrire un projet donne les mêmes octets.
"""

import json

from cstarter.config.model import Configuration, Dependency, DependencyBuild, DependencySource, Project, Target


def dump(project: Project) -> dict[str, bytes]:
    """Les fichiers de .cstarter/ : chemin relatif à la racine du projet, contenu."""
    solution = project.solution
    files = {
        ".cstarter/project.json": encode_json(
            {
                "name": project.name,
                "version": project.version,
                "generator": project.generator,
                "imported_from": project.imported_from,
            }
        ),
        ".cstarter/solution.json": encode_json(
            {
                "platforms": solution.platforms,
                "startup_target": solution.startup_target,
                "sln_output": solution.sln_output,
                "global_defines": _sorted(solution.global_defines),
                "targets": [
                    {
                        "name": entry.name,
                        "depends_on": [
                            {"target": link.target, "config_mapping": _sorted(link.config_mapping)}
                            for link in entry.depends_on
                        ],
                    }
                    for entry in solution.targets
                ],
            }
        ),
    }
    for target in project.targets.values():
        files[f".cstarter/targets/{target.name}.json"] = encode_json(_target(target))
    return files


def _target(target: Target) -> dict:
    sources = target.sources
    data = {
        "name": target.name,
        "type": target.type,
        "subsystem": target.subsystem,
        "standard": target.standard,
        "c_standard": target.c_standard,
        "vcxproj_dir": target.vcxproj_dir,
        "public_headers": target.public_headers,
        "pch": None if target.pch is None else {"header": target.pch.header, "source": target.pch.source},
        "sources": {
            "mode": sources.mode,
            "dirs": sources.dirs,
            "files": sources.files,
            "include_dirs": sources.include_dirs,
            "exclude": sources.exclude,
        },
        "output": {"bin_dir": target.output.bin_dir, "obj_dir": target.output.obj_dir},
        "debugger": {
            "working_dir": target.debugger.working_dir,
            "arguments": target.debugger.arguments,
            "environment": _sorted(target.debugger.environment),
        },
    }
    if target.guid is not None:
        data["guid"] = target.guid
    data["configurations"] = [_configuration(c) for c in target.configurations]
    data["dependencies"] = {
        name: [{"name": entry.name, "version": entry.version} for entry in entries]
        for name, entries in sorted(target.dependencies.items())
    }
    return data


def _configuration(configuration: Configuration) -> dict:
    return {
        "name": configuration.name,
        "optimization": configuration.optimization,
        "warning_level": configuration.warning_level,
        "runtime_library": configuration.runtime_library,
        "debug_info": configuration.debug_info,
        "defines": _sorted(configuration.defines),
        "whole_program_opt": configuration.whole_program_opt,
        "function_level_linking": configuration.function_level_linking,
        "link_time_code_gen": configuration.link_time_code_gen,
        "compiler_options": configuration.compiler_options,
        "linker_options": configuration.linker_options,
    }


def dump_dependency(dependency: Dependency) -> bytes:
    """Le metadata.json d'une entrée du cache."""
    return encode_json(
        {
            "name": dependency.name,
            "version": dependency.version,
            "nature": dependency.nature,
            "source": _dependency_source(dependency.source, lock=False),
            "build": _dependency_build(dependency.build),
            "libs": dependency.libs,
            "requires": dependency.requires,
            "created_at": dependency.created_at,
        }
    )


def lock_entry(dependency: Dependency) -> dict:
    """L'entrée du verrou qui décrit dependency : ni chemin absolu, ni date. requires n'y
    figure que s'il nomme une entrée."""
    data = {
        "nature": dependency.nature,
        "resolvable": dependency.source.resolvable,
        "source": _dependency_source(dependency.source, lock=True),
        "build": _dependency_build(dependency.build),
    }
    if dependency.requires:
        data["requires"] = dependency.requires
    return data


def dump_lock(entries: dict[str, object]) -> bytes:
    """dependencies.lock.json : ses entrées, triées par name@version."""
    return encode_json(_sorted(entries))


def _dependency_source(source: DependencySource, lock: bool) -> dict:
    """Les champs qui ont une valeur. Le verrou n'a ni chemin d'origine ni resolvable, qu'il porte
    au niveau de l'entrée."""
    data = {
        "type": source.type,
        "url": source.url,
        "tag": source.tag,
        "commit": source.commit,
        "sha256": source.sha256,
        "tree_sha256": source.tree_sha256,
        "port": source.port,
        "baseline": source.baseline,
        "ref": source.ref,
        "original_path": None if lock else source.original_path,
    }
    data = {key: value for key, value in data.items() if value is not None}
    if not lock:
        data["resolvable"] = source.resolvable
    return data


def _dependency_build(build: DependencyBuild) -> dict:
    """runtime et toolset sont absents quand ils valent None, pour un header-only par exemple."""
    data = {"system": build.system, "flags": build.flags, "platforms": build.platforms}
    if build.runtime is not None:
        data["runtime"] = build.runtime
    if build.toolset is not None:
        data["toolset"] = build.toolset
    return data


def _sorted(mapping: dict) -> dict:
    return dict(sorted(mapping.items()))


def encode_json(data: object) -> bytes:
    """data écrit comme tout JSON de .cstarter/ : le pilote de fusion s'en sert aussi."""
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
