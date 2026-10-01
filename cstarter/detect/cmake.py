"""Le détecteur CMake.

CStarter configure le projet dans un dossier temporaire avec une requête codemodel-v2 du File
API de CMake, puis lit la réponse : pour chaque cible, son type, ses sources, ses includes, ses
defines et ses options, dans chacune de ses configurations. C'est exact par construction, mais
la configuration exécute le code du projet : sans l'accord de l'utilisateur, CMakeLists.txt
attend dans pending. Quand CMake manque, un parseur partiel lit les commandes courantes à
arguments littéraux, et signale le reste.
"""

import os
import posixpath
import re
from pathlib import Path

from cstarter import config
from cstarter.detect import flags
from cstarter.errors import ToolchainError
from cstarter.language import t
from cstarter.toolchain.cmake import file_api, find_cmake

_TYPES = {"EXECUTABLE": "executable", "STATIC_LIBRARY": "static_lib", "SHARED_LIBRARY": "dynamic_lib", "MODULE_LIBRARY": "dynamic_lib"}
_CXX_STANDARDS = ("14", "17", "20", "23")
# Les cibles que CMake ajoute de lui-même.
_OWN_TARGETS = ("ALL_BUILD", "ZERO_CHECK", "INSTALL", "PACKAGE", "RUN_TESTS")
_EXTENSIONS = config.COMPILED + config.HEADERS + config.RESOURCES + config.DEFINITIONS


def detect(folder: Path, execute: bool = False) -> config.Detection | None:
    """Le projet CMake de folder, ou None s'il n'a pas de CMakeLists.txt à sa racine."""
    if not (folder / "CMakeLists.txt").is_file():
        return None
    files = [name for name in ("CMakeLists.txt", "CMakePresets.json", "CMakeUserPresets.json") if (folder / name).is_file()]
    try:
        find_cmake()
    except ToolchainError:
        return _parse(folder, files)
    if not execute:
        pending = [t(
            "CMakeLists.txt : CMake le configure, ce qui exécute le code du projet",
            "CMakeLists.txt: CMake configures it, which runs the project's code",
        )]
        return config.Detection(targets=[], notes=[], imported_from="cmake", pending=pending, files=files)
    try:
        replies = file_api(folder)
    except ToolchainError as error:
        return config.Detection(targets=[], notes=[t(
            f"CMakeLists.txt non lu : {error}",
            f"CMakeLists.txt not read: {error}",
        )], imported_from="cmake", files=files)
    return _codemodel(folder, replies, files)


def _codemodel(folder: Path, replies: dict[str, object], files: list[str]) -> config.Detection:
    """Le modèle partiel que donne la réponse du File API."""
    index = next(value for name, value in replies.items() if name.startswith("index-"))
    codemodel = replies[index["reply"]["client-cstarter"]["query.json"]["responses"][0]["jsonFile"]]
    source = codemodel["paths"]["source"]
    notes: list[str] = []
    targets: dict[str, config.Target] = {}
    dependencies: dict[str, list[str]] = {}
    ids: dict[str, str] = {}
    libraries = {
        Path(artifact["path"]).name.lower()
        for entry in codemodel["configurations"][0]["targets"]
        for artifact in replies[entry["jsonFile"]].get("artifacts", [])
        if artifact["path"].lower().endswith(".lib")
    }
    files += [posixpath.join(d["source"], "CMakeLists.txt") for d in codemodel["configurations"][0]["directories"] if d["source"] != "."]
    for c in codemodel["configurations"]:
        for entry in c["targets"]:
            data = replies[entry["jsonFile"]]
            name, kind = data["name"], data["type"]
            if kind not in _TYPES:
                if name not in _OWN_TARGETS:
                    notes.append(t(f"{name} : cible {kind} non traduite", f"{name}: {kind} target not translated"))
                continue
            if name not in targets:
                label = name if config.NAME.fullmatch(name) else config.safe_name(name)
                if label != name:
                    notes.append(t(f"{name} : nom invalide, devenu {label}", f"{name}: invalid name, now {label}"))
                target = config.new_target(label, _TYPES[kind])
                target.standard = "c++14"  # celui de MSVC, quand CMake n'en impose pas
                target.configurations = []
                target.sources = config.Sources(mode="manual", dirs=[], files=[], include_dirs=[], exclude=[])
                target.debugger.working_dir = data["paths"]["source"]
                targets[name] = target
                if kind == "MODULE_LIBRARY":
                    notes.append(t(f"{name} : bibliothèque MODULE reprise comme dynamic_lib", f"{name}: MODULE library kept as dynamic_lib"))
            target = targets[name]
            ids[data["id"]] = name
            dependencies[name] = [dependency["id"] for dependency in data.get("dependencies", [])]
            target.configurations.append(_configuration(c["name"], data, target, folder, source, libraries, notes))
    links = {}
    for name, target in targets.items():
        links[target.name] = []
        for identifier in dependencies[name]:
            dependency = ids.get(identifier)
            if dependency is None:
                continue
            if targets[dependency].type == "executable":
                notes.append(
                    t(f"{name} : dépendance d'ordre vers {dependency} non traduite", f"{name}: order dependency on {dependency} not translated")
                )
                continue
            links[target.name].append(config.Link(target=targets[dependency].name, config_mapping={}))
    for target in targets.values():
        target.sources.files = sorted(set(target.sources.files))
    solution = config.Solution(
        platforms=["x64"],
        startup_target=next((target.name for target in targets.values() if target.type == "executable"), None),
        sln_output=".",
        global_defines={},
        targets=[config.SolutionTarget(name=target.name, depends_on=links[target.name]) for target in targets.values()],
    )
    project = codemodel["configurations"][0]["projects"][0]["name"]
    notes = list(dict.fromkeys(notes))
    return config.Detection(
        targets=list(targets.values()),
        notes=notes,
        imported_from="cmake",
        name=config.safe_name(project),
        solution=solution,
        files=sorted(set(files)),
    )


def _configuration(
    name: str,
    data: dict,
    target: config.Target,
    folder: Path,
    source: str,
    libraries: set[str],
    notes: list[str],
) -> config.Configuration:
    """La configuration name de la cible, d'après ses groupes de compilation et son link. Elle
    remplit aussi les sources et les dossiers d'include du target."""
    configuration = config.Configuration(
        name=name,
        optimization="disabled",
        warning_level="Level1",
        runtime_library="MDd" if name == "Debug" else "MD",
        debug_info=False,
        defines={},
        whole_program_opt=False,
        function_level_linking=False,
        link_time_code_gen=False,
        compiler_options=[],
        linker_options=[],
    )
    where = f"{target.name} ({name})"
    compiled = [group for group in data.get("compileGroups", []) if group["language"] in ("C", "CXX")]
    if len({group["language"] for group in compiled}) < len(compiled):
        notes.append(
            t(
                f"{target.name} : des sources ont leurs propres options, non traduites",
                f"{target.name}: some sources have their own options, not translated",
            )
        )
    # Les options sont celles des sources C++, ou à défaut des sources C.
    group = next((group for group in compiled if group["language"] == "CXX"), compiled[0] if compiled else {})
    tokens = " ".join(fragment["fragment"] for fragment in group.get("compileCommandFragments", [])).split()
    flags.compiler(tokens, configuration, target, where, notes)
    for item in group.get("defines", []):
        found = flags.define(item["define"])
        if found is None:
            notes.append(t(f"{where} : define {item['define']} non traduit", f"{where}: define {item['define']} not translated"))
        else:
            configuration.defines[found[0]] = found[1]
    for include in group.get("includes", []):
        path = _relative(folder, source, include["path"])
        if path is None:
            notes.append(
                t(
                    f"{target.name} : dossier d'include {include['path']} hors du projet, non traduit",
                    f"{target.name}: include folder {include['path']} outside the project, not translated",
                )
            )
        elif path not in target.sources.include_dirs:
            target.sources.include_dirs.append(path)
    for group in compiled:
        standard = group.get("languageStandard", {}).get("standard")
        if group["language"] == "CXX" and standard in _CXX_STANDARDS:
            target.standard = f"c++{standard}"
        elif group["language"] == "C" and standard in ("11", "17"):
            target.c_standard = f"c{standard}"
    # Le link reprend les options de compilation, que link.exe ne reçoit pas de MSBuild.
    flags.linker(
        [
            token
            for fragment in data.get("link", {}).get("commandFragments", [])
            for token in fragment["fragment"].split()
            if token not in tokens and not (fragment["role"] == "libraries" and _is_target(token, libraries))
        ],
        configuration,
        target,
        where,
        notes,
    )
    for fragment in data.get("archive", {}).get("commandFragments", []):
        if not fragment["fragment"].lower().startswith("/machine:"):
            notes.append(
                t(
                    f"{where} : option du bibliothécaire {fragment['fragment']} non traduite",
                    f"{where}: librarian option {fragment['fragment']} not translated",
                )
            )
    for item in data.get("sources", []):
        path = _relative(folder, source, item["path"])
        if item.get("isGenerated"):
            notes.append(
                t(
                    f"{target.name} : {item['path']} est produit par CMake, non traduit",
                    f"{target.name}: {item['path']} is produced by CMake, not translated",
                )
            )
        elif path is None:
            notes.append(
                t(
                    f"{target.name} : {item['path']} hors du projet, non traduit",
                    f"{target.name}: {item['path']} outside the project, not translated",
                )
            )
        elif not path.lower().endswith(_EXTENSIONS):
            notes.append(
                t(f"{target.name} : {path} non traduit", f"{target.name}: {path} not translated")
            )
        else:
            target.sources.files.append(path)
    return configuration


def _is_target(token: str, libraries: set[str]) -> bool:
    """Le .lib d'une cible du projet : le lien entre targets le remplace."""
    return bool(re.search(r"[/\\]", token)) and Path(token.replace("\\", "/")).name.lower() in libraries


def _relative(folder: Path, source: str, path: str) -> str | None:
    """path, relatif à source ou absolu, exprimé depuis folder à barres obliques ; None s'il en sort."""
    try:
        relative = os.path.relpath(os.path.normpath(os.path.join(source, path)), folder).replace("\\", "/")
    except ValueError:
        return None
    return None if relative.split("/")[0] == ".." else relative


# Le parseur partiel, en secours quand CMake manque.

_COMMAND = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(((?:[^()]|\([^()]*\))*)\)", re.DOTALL)
_ARGUMENT = re.compile(r'"((?:[^"\\]|\\.)*)"|([^\s"]+)')
_SCOPES = ("PUBLIC", "PRIVATE", "INTERFACE")
# Les configurations de CMake et leurs options par défaut avec MSVC.
_DEFAULTS = (
    ("Debug", "disabled", "MDd", True, "/Ob0", {}),
    ("Release", "max_speed", "MD", False, "/Ob2", {"NDEBUG": None}),
    ("MinSizeRel", "min_size", "MD", False, "/Ob1", {"NDEBUG": None}),
    ("RelWithDebInfo", "max_speed", "MD", True, "/Ob1", {"NDEBUG": None}),
)


def _parse(folder: Path, files: list[str]) -> config.Detection:
    """Le modèle partiel que donne une lecture sans CMake : project, add_subdirectory,
    add_executable, add_library, target_sources, target_include_directories,
    target_compile_definitions, target_link_libraries, target_compile_features et
    set(CMAKE_CXX_STANDARD), à arguments littéraux. Le reste est signalé."""
    notes = [t(
        "CMake introuvable : un parseur partiel lit CMakeLists.txt, sans évaluer ni variable ni condition",
        "CMake not found: a partial parser reads CMakeLists.txt, evaluating neither variables nor conditions",
    )]
    targets: dict[str, config.Target] = {}
    uses: dict[str, list[str]] = {}
    unknown: set[str] = set()
    project, standard = folder.resolve().name, "c++14"
    queue = ["."]
    while queue:
        directory = queue.pop(0)
        where = posixpath.normpath(f"{directory}/CMakeLists.txt")
        if not (folder / where).is_file():
            notes.append(t(f"{where} introuvable", f"{where} not found"))
            continue
        files.append(where)
        for command, raw in _COMMAND.findall(_uncomment((folder / where).read_text(encoding="utf-8", errors="replace"))):
            command = command.lower()
            args = [quoted or bare for quoted, bare in _ARGUMENT.findall(raw)]
            if any("${" in arg or "$<" in arg for arg in args) and command != "project":
                notes.append(
                    t(
                        f"{where} : {command}() emploie une variable ou une expression, non traduit",
                        f"{where}: {command}() uses a variable or an expression, not translated",
                    )
                )
                continue
            if command == "project" and args:
                project = args[0]
            elif command == "add_subdirectory" and args:
                queue.append(posixpath.normpath(f"{directory}/{args[0]}"))
            elif command in ("add_executable", "add_library") and args:
                _add(command, args, directory, standard, targets, notes)
            elif command in ("target_sources", "target_include_directories", "target_compile_definitions",
                             "target_link_libraries", "target_compile_features") and args:
                if args[0] not in targets:
                    notes.append(t(f"{command}({args[0]}) : cible inconnue, non traduit", f"{command}({args[0]}): unknown target, not translated"))
                else:
                    _apply(command, targets[args[0]], args[1:], directory, uses, notes)
            elif command == "set" and args[:1] == ["CMAKE_CXX_STANDARD"] and len(args) > 1 and args[1] in _CXX_STANDARDS:
                standard = f"c++{args[1]}"  # il vaut pour les cibles créées ensuite, comme dans CMake
            elif command != "cmake_minimum_required":
                unknown.add(command)
    links = {name: [] for name in targets}
    for name, items in uses.items():
        for item in items:
            if item in targets and targets[item].type != "executable":
                links[name].append(config.Link(target=item, config_mapping={}))
            elif "::" in item or item in targets:
                notes.append(t(f"{name} : dépendance {item} non traduite", f"{name}: dependency {item} not translated"))
            else:
                for c in targets[name].configurations:
                    c.linker_options.append(item if item.lower().endswith(".lib") else f"{item}.lib")
    if unknown:
        notes.append(
            t(f"commandes CMake non traduites : {', '.join(sorted(unknown))}", f"CMake commands not translated: {', '.join(sorted(unknown))}")
        )
    solution = config.Solution(
        platforms=["x64"],
        startup_target=next((name for name, target in targets.items() if target.type == "executable"), None),
        sln_output=".",
        global_defines={},
        targets=[config.SolutionTarget(name=name, depends_on=links[name]) for name in targets],
    )
    return config.Detection(
        targets=list(targets.values()),
        notes=notes,
        imported_from="cmake",
        name=config.safe_name(project),
        solution=solution,
        files=sorted(set(files)),
    )


def _add(
    command: str, args: list[str], directory: str, standard: str, targets: dict[str, config.Target], notes: list[str]
) -> None:
    """Une cible de add_executable ou de add_library, aux configurations de CMake."""
    name, rest = args[0], args[1:]
    keywords = {arg for arg in rest if arg.isupper()}
    if keywords & {"IMPORTED", "ALIAS", "OBJECT", "INTERFACE"} or not config.NAME.fullmatch(name):
        notes.append(t(f"{command}({name}) non traduit", f"{command}({name}) not translated"))
        return
    if command == "add_executable":
        target = config.new_target(name, "executable", "windows" if "WIN32" in keywords else "console")
    else:
        target = config.new_target(name, "dynamic_lib" if keywords & {"SHARED", "MODULE"} else "static_lib")
        if not keywords & {"STATIC", "SHARED", "MODULE"}:
            notes.append(
                t(
                    f"{name} : ni STATIC ni SHARED, repris en static_lib sans lire BUILD_SHARED_LIBS",
                    f"{name}: neither STATIC nor SHARED, kept as static_lib without reading BUILD_SHARED_LIBS",
                )
            )
    target.standard = standard
    target.configurations = [
        config.Configuration(
            name=c,
            optimization=optimization,
            warning_level="Level1",
            runtime_library=runtime,
            debug_info=debug,
            defines={"WIN32": None, "_WINDOWS": None, **defines},
            whole_program_opt=False,
            function_level_linking=False,
            link_time_code_gen=False,
            compiler_options=[inline],
            linker_options=[],
        )
        for c, optimization, runtime, debug, inline, defines in _DEFAULTS
    ]
    target.sources = config.Sources(mode="manual", dirs=[], files=[], include_dirs=[], exclude=[])
    target.debugger.working_dir = directory
    targets[name] = target
    _apply("target_sources", target, ["PRIVATE", *(arg for arg in rest if arg not in keywords)], directory, {}, notes)


def _apply(command: str, target: config.Target, args: list[str], directory: str, uses: dict[str, list[str]], notes: list[str]) -> None:
    """Une commande target_* à arguments littéraux, sur target."""
    scope = "PRIVATE"
    for arg in args:
        if arg in _SCOPES or arg in ("SYSTEM", "BEFORE", "AFTER"):
            scope = arg if arg in _SCOPES else scope
            continue
        path = posixpath.normpath(posixpath.join(directory, arg))
        if command == "target_sources":
            if path.lower().endswith(_EXTENSIONS):
                target.sources.files.append(path)
            else:
                notes.append(
                    t(f"{target.name} : {path} non traduit", f"{target.name}: {path} not translated")
                )
        elif command == "target_include_directories":
            if scope != "PRIVATE" and target.public_headers is None:
                target.public_headers = path
            elif path not in target.sources.include_dirs:
                target.sources.include_dirs.append(path)
        elif command == "target_compile_definitions":
            found = flags.define(arg.removeprefix("-D"))
            if found is None:
                notes.append(t(f"{target.name} : define {arg} non traduit", f"{target.name}: define {arg} not translated"))
                continue
            for c in target.configurations:
                c.defines[found[0]] = found[1]
        elif command == "target_link_libraries":
            uses.setdefault(target.name, []).append(arg)
        elif command == "target_compile_features" and re.fullmatch(r"cxx_std_(14|17|20|23)", arg):
            target.standard = f"c++{arg[8:]}"
        else:
            notes.append(t(f"{target.name} : {command}({arg}) non traduit", f"{target.name}: {command}({arg}) not translated"))


def _uncomment(text: str) -> str:
    """text sans ses commentaires #, hors des chaînes entre guillemets."""
    lines = []
    for line in text.splitlines():
        quoted = False
        for index, char in enumerate(line):
            if char == '"' and (index == 0 or line[index - 1] != "\\"):
                quoted = not quoted
            elif char == "#" and not quoted:
                line = line[:index]
                break
        lines.append(line)
    return "\n".join(lines)
