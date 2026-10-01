"""Le détecteur de solutions Visual Studio.

Le .sln donne les targets, les configurations et les plateformes, et sa section
ProjectConfigurationPlatforms les config_mapping. Chaque .vcxproj donne, pour chaque couple
configuration et plateforme, ses sources, ses dossiers d'include, ses defines, son type, son
runtime, ses références à d'autres projets et ses réglages. Les GUID sont conservés.
Seules les conditions '$(Configuration)|$(Platform)'=='…' sont évaluées. Une
macro inconnue, un .props importé ou un réglage sans équivalent dans le modèle sont signalés,
jamais devinés.

Le modèle n'a qu'un jeu de réglages par configuration : ceux de x64 servent, et un écart avec
une autre plateforme est signalé. Le détecteur de Premake lit de même la solution que premake5
produit.
"""

import os
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path, PureWindowsPath

from cstarter import config
from cstarter.detect import flags
from cstarter.errors import ConfigError
from cstarter.language import t

_CPP_PROJECT = "8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942"
_SOLUTION_FOLDER = "2150E333-8FDC-42A3-9474-1A3956D46DE8"
_PROJECT = re.compile(r'^Project\("\{([0-9A-Fa-f-]+)\}"\)\s*=\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"(\{[0-9A-Fa-f-]+\})"', re.MULTILINE)
_SOLUTION_PLATFORM = re.compile(r"^\s*([^|=\r\n]+?)\|([^=\s]+)\s*=", re.MULTILINE)
_PROJECT_PLATFORM = re.compile(
    r"^\s*(\{[0-9A-Fa-f-]+\})\.([^|\r\n]+)\|([^.\r\n]+)\.(ActiveCfg|Build\.0)\s*=\s*([^|\r\n]+)\|", re.MULTILINE
)
_CONDITION = re.compile(r"\s*'\$\(Configuration\)\|\$\(Platform\)'\s*==\s*'([^|']*)\|([^']*)'\s*")
_MACRO = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)")
_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
# Les noms de MSBuild, en minuscules, vers ceux du modèle ; x86 est aussi le nom de Win32 dans une solution.
_PLATFORMS = {name.lower(): platform for platform, name in config.MSVC_PLATFORMS.items()} | {"x86": "x86"}
_TYPES = {"application": "executable", "staticlibrary": "static_lib", "dynamiclibrary": "dynamic_lib"}
_OPTIMIZATIONS = {"disabled": "disabled", "minspace": "min_size", "maxspeed": "max_speed", "full": "full"}
_RUNTIMES = {name.lower(): runtime for runtime, name in config.MSVC_RUNTIMES.items()}
_STANDARDS = {"default": "c++14", "stdcpp14": "c++14", "stdcpp17": "c++17", "stdcpp20": "c++20", "stdcpp23": "c++23", "stdcpplatest": "c++latest"}
_C_STANDARDS = {"default": None, "stdc11": "c11", "stdc17": "c17"}
_ITEMS = ("ClCompile", "ClInclude", "ResourceCompile")
_IGNORED_ITEMS = ("None", "Text", "Image")
_STANDARD_IMPORTS = {
    r"$(vctargetspath)\microsoft.cpp.default.props",
    r"$(vctargetspath)\microsoft.cpp.props",
    r"$(vctargetspath)\microsoft.cpp.targets",
    r"$(userrootdir)\microsoft.cpp.$(platform).user.props",
}
# Les réglages que le détecteur traduit. Les autres sont signalés.
_HANDLED = {
    "ClCompile": {
        "Optimization", "WarningLevel", "RuntimeLibrary", "DebugInformationFormat", "WholeProgramOptimization",
        "FunctionLevelLinking", "PreprocessorDefinitions", "AdditionalIncludeDirectories", "LanguageStandard",
        "LanguageStandard_C", "PrecompiledHeader", "PrecompiledHeaderFile", "AdditionalOptions", "SDLCheck",
        "ConformanceMode", "TreatWarningAsError", "MultiProcessorCompilation", "IntrinsicFunctions",
        "DisableSpecificWarnings", "ExceptionHandling", "BasicRuntimeChecks", "SupportJustMyCode",
    },
    "Link": {
        "SubSystem", "GenerateDebugInformation", "LinkTimeCodeGeneration", "EnableCOMDATFolding",
        "OptimizeReferences", "AdditionalDependencies", "AdditionalOptions", "ModuleDefinitionFile", "TargetMachine",
    },
}
_PROPERTIES = {
    "ConfigurationType", "UseDebugLibraries", "PlatformToolset", "CharacterSet", "WholeProgramOptimization",
    "LinkIncremental", "ProjectGuid", "RootNamespace", "Keyword", "VCProjectVersion", "WindowsTargetPlatformVersion",
    "ProjectName",
}
# Les sorties : CStarter fixe les siennes.
_OUTPUTS = {
    "OutDir", "IntDir", "TargetName", "TargetExt", "OutputFile", "ProgramDatabaseFile", "ImportLibrary",
    "ProgramDataBaseFileName", "ObjectFileName", "AssemblerListingLocation",
}


def detect(folder: Path, execute: bool = False) -> config.Detection | None:
    """La première solution Visual Studio à la racine de folder, ou None s'il n'en a pas."""
    solutions = sorted(folder.glob("*.sln"))
    if not solutions:
        return None
    found = read_solution(folder, solutions[0])
    found.notes += [t(f"{path.name} : solution de plus, non lue", f"{path.name}: extra solution, not read") for path in solutions[1:]]
    return found


def read_solution(root: Path, path: Path) -> config.Detection:
    """Le modèle partiel de la solution path. Ses chemins sont relatifs à root."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    notes: list[str] = []
    projects = []
    for kind, name, relative, guid in _PROJECT.findall(text):
        if kind.upper() == _SOLUTION_FOLDER:
            notes.append(t(f"{path.name} : dossier de solution {name} non traduit", f"{path.name}: solution folder {name} not translated"))
        elif kind.upper() == _CPP_PROJECT or relative.lower().endswith(".vcxproj"):
            projects.append((name, path.parent / PureWindowsPath(relative), guid.upper()))
        else:
            notes.append(
                t(
                    f"{path.name} : projet {name} ({relative}) non traduit, seul le C++ l'est",
                    f"{path.name}: project {name} ({relative}) not translated, only C++ is",
                )
            )
    pairs = _SOLUTION_PLATFORM.findall(_section(text, "SolutionConfigurationPlatforms"))
    active: dict[str, dict[tuple[str, str], list]] = {}
    for guid, s, p, kind, configuration in _PROJECT_PLATFORM.findall(_section(text, "ProjectConfigurationPlatforms")):
        state = active.setdefault(guid.upper(), {}).setdefault((s.strip(), p.strip()), [None, False])
        if kind == "ActiveCfg":
            state[0] = configuration.strip()
        else:
            state[1] = True
    platforms = []
    for p in dict.fromkeys(p for _, p in pairs):
        if p.lower() not in _PLATFORMS:
            notes.append(t(f"{path.name} : plateforme {p} non traduite", f"{path.name}: platform {p} not translated"))
        elif _PLATFORMS[p.lower()] not in platforms:
            platforms.append(_PLATFORMS[p.lower()])
    platforms = platforms or ["x64"]
    reference = "x64" if "x64" in platforms else platforms[0]
    sln_platform = next((p for _, p in pairs if _PLATFORMS.get(p.lower()) == reference), reference)
    targets, references, vcxprojs, files = [], {}, {}, [_relative(root, path)]
    for name, vcxproj, guid in projects:
        found = _target(root, path.parent, name, vcxproj, guid, platforms, notes)
        if found is not None:
            target, refs = found
            targets.append(target)
            references[target.name] = refs
            vcxprojs[os.path.normcase(os.path.abspath(vcxproj))] = target.name
            files += [_relative(root, p) for p in (vcxproj, Path(f"{vcxproj}.filters"), Path(f"{vcxproj}.user")) if p.is_file()]
    by_guid = {target.guid: target.name for target in targets}
    configurations = list(dict.fromkeys(s.strip() for s, _ in pairs))
    links = {target.name: [] for target in targets}
    for target in targets:
        for guid, reference_path in references[target.name]:
            dependency = by_guid.get(guid) or vcxprojs.get(os.path.normcase(reference_path))
            if dependency is None:
                notes.append(
                    t(
                        f"{target.name} : référence à {Path(reference_path).name}, hors de la solution, non traduite",
                        f"{target.name}: reference to {Path(reference_path).name}, outside the solution, not translated",
                    )
                )
                continue
            other = next(t for t in targets if t.name == dependency)
            links[target.name].append(
                config.Link(target=dependency, config_mapping=_mapping(target, other, configurations, active, sln_platform, notes))
            )
    solution = config.Solution(
        platforms=platforms,
        startup_target=next((target.name for target in targets if target.type == "executable"), None),
        sln_output=".",
        global_defines={},
        targets=[config.SolutionTarget(name=target.name, depends_on=links[target.name]) for target in targets],
    )
    notes += _matrix_notes(root, targets, solution, configurations, active, sln_platform)
    return config.Detection(
        targets=targets, notes=notes, imported_from="vcxproj", name=config.safe_name(path.stem), solution=solution, files=files
    )


def _mapping(
    consumer: config.Target,
    dependency: config.Target,
    configurations: list[str],
    active: dict[str, dict[tuple[str, str], list]],
    platform: str,
    notes: list[str],
) -> dict[str, str]:
    """La correspondance de configurations du lien, d'après ce que la solution construit."""
    mapping: dict[str, str] = {}
    mine, theirs = active.get(consumer.guid, {}), active.get(dependency.guid, {})
    for s in configurations:
        built, wanted = mine.get((s, platform)), theirs.get((s, platform))
        if not built or not built[1] or not wanted or built[0] == wanted[0]:
            continue
        if mapping.setdefault(built[0], wanted[0]) != wanted[0]:
            notes.append(
                t(
                    f"{consumer.name} vers {dependency.name} : {built[0]} construit tantôt {mapping[built[0]]}, tantôt {wanted[0]}",
                    f"{consumer.name} to {dependency.name}: {built[0]} builds sometimes {mapping[built[0]]}, sometimes {wanted[0]}",
                )
            )
    consumer_names, dependency_names = {c.name for c in consumer.configurations}, {c.name for c in dependency.configurations}
    valid = {a: b for a, b in mapping.items() if a in consumer_names and b in dependency_names}
    if valid != mapping:
        notes.append(
            t(
                f"{consumer.name} vers {dependency.name} : correspondance vers des configurations absentes, non reprise",
                f"{consumer.name} to {dependency.name}: mapping to missing configurations, not kept",
            )
        )
    return valid


def _matrix_notes(
    root: Path,
    targets: list[config.Target],
    solution: config.Solution,
    configurations: list[str],
    active: dict[str, dict[tuple[str, str], list]],
    platform: str,
) -> list[str]:
    """Ce que la solution construisait dans chaque configuration et que la correspondance de configurations
    construira autrement."""
    project = config.Project(
        root=root,
        name="import",
        version="0.1.0",
        generator="vs2022",
        imported_from="vcxproj",
        solution=solution,
        targets={target.name: target for target in targets},
        vendored=[],
    )
    try:
        matrix = config.build_matrix(project)
    except ConfigError as error:
        return [t(f"correspondance des configurations : {error}", f"configuration mapping: {error}")]
    notes = []
    for s in configurations:
        if s not in matrix:
            notes.append(
                t(
                    f"configuration de solution {s} non reprise : celles de CStarter sont celles des targets",
                    f"solution configuration {s} not kept: CStarter's are those of the targets",
                )
            )
            continue
        for target in targets:
            state = active.get(target.guid, {}).get((s, platform))
            before = state[0] if state and state[1] else None
            after = matrix[s][target.name]
            if before != after:
                was, will = f"en {before}" if before else "pas", f"en {after}" if after else "pas"
                notes.append(
                    t(
                        f"{s} : {target.name} se construisait {was}, il se construira {will}",
                        f"{s}: {target.name} was built in {was}, it will be built in {will}",
                    )
                )
    return notes


def _target(
    root: Path, solution_dir: Path, name: str, path: Path, guid: str, platforms: list[str], notes: list[str]
) -> tuple[config.Target, list[tuple[str | None, str]]] | None:
    """Le target que décrit le .vcxproj path, et ses références (GUID, chemin absolu), ou None s'il ne
    se traduit pas."""
    where = _relative(root, path)
    if not path.is_file():
        notes.append(t(f"{name} : {where} introuvable", f"{name}: {where} not found"))
        return None
    try:
        xml = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as error:
        notes.append(t(f"{where} : XML illisible, {error}", f"{where}: unreadable XML, {error}"))
        return None
    for element in xml.iter():
        element.tag = element.tag.rpartition("}")[2]
    here = path.parent
    pairs = [(item.findtext("Configuration", ""), item.findtext("Platform", "")) for item in xml.iter("ProjectConfiguration")]
    if not pairs:
        notes.append(t(f"{where} : aucune configuration, non traduit", f"{where}: no configuration, not translated"))
        return None
    mine: dict[str, None] = {}  # les notes du target, sans doublon
    unevaluated: set[str] = set()
    evaluated = {pair: _evaluate(xml, *pair, unevaluated) for pair in pairs}
    types = {_TYPES.get(properties.get("ConfigurationType", "Application").lower()) for properties, _ in evaluated.values()}
    if None in types or len(types) > 1:
        notes.append(
            t(
                f"{name} : type de configuration non traduit ({', '.join(sorted(str(kind) for kind in types))})",
                f"{name}: configuration type not translated ({', '.join(sorted(str(kind) for kind in types))})",
            )
        )
        return None
    label = name if config.NAME.fullmatch(name) else config.safe_name(name)
    if label != name:
        mine[t(f"nom invalide, devenu {label}", f"invalid name, now {label}")] = None
    target = config.new_target(label, types.pop())
    target.guid = guid
    names = list(dict.fromkeys(c for c, _ in pairs))

    def reference(c: str) -> tuple[str, str]:
        candidates = [pair for pair in pairs if pair[0] == c]
        return next((pair for pair in candidates if _PLATFORMS.get(pair[1].lower()) == "x64"), candidates[0])

    for c in names:
        if any(evaluated[pair] != evaluated[reference(c)] for pair in pairs if pair[0] == c):
            mine[t(
                f"réglages de {c} différents selon la plateforme : ceux de {reference(c)[1]} sont repris",
                f"settings of {c} differ between platforms: those of {reference(c)[1]} are kept",
            )] = None
    for platform in platforms:
        if platform not in {_PLATFORMS.get(p.lower()) for _, p in pairs}:
            mine[t(
                f"pas de plateforme {platform} : les réglages de {reference(names[0])[1]} serviront",
                f"no platform {platform}: the settings of {reference(names[0])[1]} will be used",
            )] = None
    for condition in sorted(unevaluated):
        mine[t(f"condition non évaluée : {condition}", f"condition not evaluated: {condition}")] = None
    for element in xml.iter("Import"):
        if element.get("Project", "").lower() not in _STANDARD_IMPORTS:
            mine[t(f"importe {element.get('Project')}, non lu", f"imports {element.get('Project')}, not read")] = None
    first = evaluated[reference(names[0])]
    standards = {evaluated[reference(c)][1].get("ClCompile", {}).get("LanguageStandard") or "Default" for c in names}
    c_standards = {evaluated[reference(c)][1].get("ClCompile", {}).get("LanguageStandard_C") or "Default" for c in names}
    if len(standards) > 1 or len(c_standards) > 1:
        mine[t(
            "standard différent selon la configuration : celui de la première est repris",
            "standard differs between configurations: the first one's is kept",
        )] = None
    standard = first[1].get("ClCompile", {}).get("LanguageStandard") or "Default"
    c_standard = first[1].get("ClCompile", {}).get("LanguageStandard_C") or "Default"
    if standard.lower() not in _STANDARDS or c_standard.lower() not in _C_STANDARDS:
        mine[t(f"standard {standard} ou {c_standard} non traduit", f"standard {standard} or {c_standard} not translated")] = None
    target.standard = _STANDARDS.get(standard.lower(), "c++14")
    target.c_standard = _C_STANDARDS.get(c_standard.lower())
    if target.type == "executable":
        target.subsystem = "windows" if first[1].get("Link", {}).get("SubSystem", "") == "Windows" else "console"
    target.configurations = [_configuration(c, *evaluated[reference(c)], target, mine) for c in names]
    include_dirs: list[str] = []
    for c in names:
        dirs = _paths(evaluated[reference(c)][1].get("ClCompile", {}).get("AdditionalIncludeDirectories", ""), root, solution_dir, here, name, mine)
        if include_dirs and dirs != include_dirs:
            mine[t(
                "dossiers d'include différents selon la configuration : leur union est reprise",
                "include folders differ between configurations: their union is kept",
            )] = None
        include_dirs += [d for d in dirs if d not in include_dirs]
    files, creators, references = _items(xml, pairs, root, solution_dir, here, name, mine)
    definition = first[1].get("Link", {}).get("ModuleDefinitionFile")
    if definition:
        files += [p for p in _paths(definition, root, solution_dir, here, name, mine) if p not in files]
    if any(char in f for f in files for char in "[*?"):
        mine[t(
            "un nom de fichier contient [, * ou ? : sources.files le lirait comme un motif",
            "a file name contains [, * or ?: sources.files would read it as a pattern",
        )] = None
    uses = [c for c in names if evaluated[reference(c)][1].get("ClCompile", {}).get("PrecompiledHeader") == "Use"]
    if uses and len(uses) == len(names) and len(creators) == 1:
        header = first[1].get("ClCompile", {}).get("PrecompiledHeaderFile") or "pch.h"
        target.pch = config.Pch(header=header, source=creators[0])
    elif uses or creators:
        mine[t(
            "en-tête précompilé partiel ou sans source qui le crée : non traduit",
            "precompiled header partial or without a source that creates it: not translated",
        )] = None
    target.sources = config.Sources(mode="manual", dirs=[], files=sorted(set(files)), include_dirs=include_dirs, exclude=[])
    target.debugger.working_dir = _relative(root, here)
    if Path(f"{path}.user").is_file():
        mine[t(f"{Path(f'{path}.user').name} : réglages de débogage non repris", f"{Path(f'{path}.user').name}: debugging settings not kept")] = None
    notes += [t(f"{name} : {note}", f"{name}: {note}") for note in mine]
    return target, references


def _configuration(
    name: str, properties: dict[str, str], tools: dict[str, dict[str, str]], target: config.Target, notes: dict[str, None]
) -> config.Configuration:
    """La configuration name, d'après ses propriétés et ses métadonnées, les défauts de MSBuild
    comblant les absentes."""
    debug = properties.get("UseDebugLibraries", "").lower() == "true"
    wpo = properties.get("WholeProgramOptimization", "").lower() == "true"
    compile, link = tools.get("ClCompile", {}), tools.get("Link", {})
    optimization = _OPTIMIZATIONS.get((compile.get("Optimization") or ("Disabled" if debug else "MaxSpeed")).lower())
    if optimization is None:
        notes[t(
            f"{name} : optimisation {compile['Optimization']} non traduite, max_speed reprise",
            f"{name}: optimization {compile['Optimization']} not translated, max_speed kept",
        )] = None
    warning = compile.get("WarningLevel") or "Level1"
    if warning not in ("Level1", "Level2", "Level3", "Level4", "EnableAllWarnings"):
        notes[t(
            f"{name} : niveau d'avertissement {warning} non traduit, Level1 repris",
            f"{name}: warning level {warning} not translated, Level1 kept",
        )] = None
        warning = "Level1"
    runtime = _RUNTIMES.get((compile.get("RuntimeLibrary") or ("MultiThreadedDebugDLL" if debug else "MultiThreadedDLL")).lower())
    if runtime is None:
        notes[t(f"{name} : runtime {compile['RuntimeLibrary']} non traduit", f"{name}: runtime {compile['RuntimeLibrary']} not translated")] = None
    ltcg = link.get("LinkTimeCodeGeneration") or ("UseLinkTimeCodeGeneration" if wpo else "Default")
    if ltcg not in ("Default", "UseLinkTimeCodeGeneration", "UseFastLinkTimeCodeGeneration"):
        notes[t(f"{name} : génération de code au link {ltcg} non traduite", f"{name}: link-time code generation {ltcg} not translated")] = None
    configuration = config.Configuration(
        name=name,
        optimization=optimization or "max_speed",
        warning_level=warning,
        runtime_library=runtime or ("MDd" if debug else "MD"),
        debug_info=(compile.get("DebugInformationFormat") or "ProgramDatabase") != "None",
        defines=_defines(properties, compile, notes, name),
        whole_program_opt=(compile.get("WholeProgramOptimization") or str(wpo)).lower() == "true",
        function_level_linking=compile.get("FunctionLevelLinking", "").lower() == "true",
        link_time_code_gen=ltcg in ("UseLinkTimeCodeGeneration", "UseFastLinkTimeCodeGeneration"),
        compiler_options=_compiler_options(compile, debug, notes, name),
        linker_options=[],
    )
    found: list[str] = []
    flags.compiler(_tokens(compile.get("AdditionalOptions", "")), configuration, target, name, found)
    if target.type != "static_lib":
        configuration.linker_options = _linker_options(link, wpo, notes, name)
        flags.linker(_tokens(link.get("AdditionalOptions", "")), configuration, target, name, found)
        generated = link.get("GenerateDebugInformation", "true").lower() not in ("false", "no")
        if generated != configuration.debug_info:
            notes[t(
                f"{name} : informations de débogage à la compilation et au link en désaccord",
                f"{name}: debugging information disagrees between compile and link",
            )] = None
    elif tools.get("Lib"):
        notes[t(f"{name} : réglages du bibliothécaire (Lib) non traduits", f"{name}: librarian (Lib) settings not translated")] = None
    notes.update(dict.fromkeys(found))
    for key in properties:
        if key in _OUTPUTS:
            notes[t(
                "sorties (OutDir, IntDir, noms de fichiers) remplacées par celles de CStarter",
                "outputs (OutDir, IntDir, file names) replaced by CStarter's",
            )] = None
        elif key not in _PROPERTIES:
            notes[t(f"propriété {key} non traduite", f"property {key} not translated")] = None
    if properties.get("PlatformToolset", "v143") != "v143":
        notes[t(f"toolset {properties['PlatformToolset']} remplacé par v143", f"toolset {properties['PlatformToolset']} replaced by v143")] = None
    if properties.get("WindowsTargetPlatformVersion", "10.0") != "10.0":
        notes[t(
            f"SDK {properties['WindowsTargetPlatformVersion']} remplacé par 10.0, le plus récent installé",
            f"SDK {properties['WindowsTargetPlatformVersion']} replaced by 10.0, the latest installed",
        )] = None
    for tool, metadata in tools.items():
        for key in metadata:
            if key in _OUTPUTS:
                notes[t(
                    "sorties (OutDir, IntDir, noms de fichiers) remplacées par celles de CStarter",
                    "outputs (OutDir, IntDir, file names) replaced by CStarter's",
                )] = None
            elif key not in _HANDLED.get(tool, set()):
                notes[t(f"{tool}.{key} non traduit", f"{tool}.{key} not translated")] = None
    return configuration


def _defines(properties: dict[str, str], compile: dict[str, str], notes: dict[str, None], name: str) -> dict[str, config.Define]:
    """Les defines de la configuration, ceux que CharacterSet ajoute compris."""
    defines: dict[str, config.Define] = {}
    charset = properties.get("CharacterSet", "")
    if charset == "Unicode":
        defines.update({"UNICODE": None, "_UNICODE": None})
    elif charset == "MultiByte":
        defines["_MBCS"] = None
    for item in _split(compile.get("PreprocessorDefinitions", "")):
        found = flags.define(item) if "$(" not in item else None
        if found is None:
            notes[t(f"{name} : define {item} non traduit", f"{name}: define {item} not translated")] = None
        else:
            defines[found[0]] = found[1]
    return defines


def _compiler_options(compile: dict[str, str], debug: bool, notes: dict[str, None], name: str) -> list[str]:
    """Les réglages de ClCompile sans champ dans le modèle, en options de cl.exe."""
    options = [
        option
        for key, option in (
            ("SDLCheck", "/sdl"),
            ("ConformanceMode", "/permissive-"),
            ("TreatWarningAsError", "/WX"),
            ("MultiProcessorCompilation", "/MP"),
            ("IntrinsicFunctions", "/Oi"),
        )
        if compile.get(key, "").lower() == "true"
    ]
    options += [f"/wd{warning}" for warning in _split(compile.get("DisableSpecificWarnings", ""))]
    handling = compile.get("ExceptionHandling", "Sync")
    if handling in ("Async", "SyncCThrow"):
        options.append("/EHa" if handling == "Async" else "/EHs")
    elif handling not in ("Sync", ""):
        notes[t(f"{name} : gestion des exceptions {handling} non traduite", f"{name}: exception handling {handling} not translated")] = None
    if compile.get("BasicRuntimeChecks", "EnableFastChecks" if debug else "Default") != ("EnableFastChecks" if debug else "Default"):
        notes[t(
            f"{name} : BasicRuntimeChecks {compile['BasicRuntimeChecks']} non traduit",
            f"{name}: BasicRuntimeChecks {compile['BasicRuntimeChecks']} not translated",
        )] = None
    if compile.get("SupportJustMyCode", str(debug)).lower() != str(debug).lower():
        notes[t(
            f"{name} : SupportJustMyCode {compile['SupportJustMyCode']} non traduit",
            f"{name}: SupportJustMyCode {compile['SupportJustMyCode']} not translated",
        )] = None
    return options


def _linker_options(link: dict[str, str], wpo: bool, notes: dict[str, None], name: str) -> list[str]:
    """Les réglages de Link sans champ dans le modèle, en options de link.exe, avec les
    bibliothèques liées que MSBuild ne lie pas déjà."""
    options = [
        option
        for key, option in (("EnableCOMDATFolding", "/OPT:ICF"), ("OptimizeReferences", "/OPT:REF"))
        if link.get(key, str(wpo)).lower() == "true"
    ]
    for library in _split(link.get("AdditionalDependencies", "")):
        if library.lower() in flags.DEFAULT_LIBRARIES:
            continue
        if re.search(r"[/\\:$]", library):
            notes[t(
                f"{name} : bibliothèque {library} non traduite, désignée par un chemin ou une macro",
                f"{name}: library {library} not translated, named by a path or a macro",
            )] = None
        else:
            options.append(library)
    if link.get("AdditionalLibraryDirectories"):
        notes[t(
            f"{name} : dossiers de bibliothèques {link['AdditionalLibraryDirectories']} non traduits : installez ces bibliothèques dans le cache",
            f"{name}: library folders {link['AdditionalLibraryDirectories']} not translated: install these libraries in the cache",
        )] = None
    return options


def _items(
    xml: ElementTree.Element,
    pairs: list[tuple[str, str]],
    root: Path,
    solution_dir: Path,
    here: Path,
    name: str,
    notes: dict[str, None],
) -> tuple[list[str], list[str], list[tuple[str | None, str]]]:
    """Les sources, celles qui créent l'en-tête précompilé, et les références (GUID, chemin absolu)."""
    files, creators, references, special = [], [], [], []
    for group in xml.iter("ItemGroup"):
        if group.get("Condition"):
            notes[t(
                f"éléments sous condition non traduits : {group.get('Condition')}",
                f"conditional items not translated: {group.get('Condition')}",
            )] = None
            continue
        for item in group:
            include = item.get("Include", "")
            if item.tag == "ProjectConfiguration":
                continue
            if item.tag == "ProjectReference":
                references.append((item.findtext("Project", "").upper() or None, os.path.abspath(here / PureWindowsPath(include))))
                continue
            if item.tag not in _ITEMS and not (item.tag == "None" and include.lower().endswith(".def")):
                if item.tag not in _IGNORED_ITEMS:
                    notes[t(f"élément {item.tag} {include} non traduit", f"item {item.tag} {include} not translated")] = None
                continue
            for path in _paths(include, root, solution_dir, here, name, notes):
                excluded = [
                    pair
                    for pair in pairs
                    if any(
                        meta.tag == "ExcludedFromBuild" and (meta.text or "").strip().lower() == "true" and _applies(meta, *pair, set())
                        for meta in item
                    )
                ]
                if len(excluded) == len(pairs):
                    continue
                if excluded:
                    notes[t(
                        f"{path} exclu de certaines configurations seulement : il est compilé partout",
                        f"{path} excluded from some configurations only: it is compiled everywhere",
                    )] = None
                files.append(path)
                for meta in item:
                    text = (meta.text or "").strip()
                    if meta.tag == "PrecompiledHeader" and text == "Create":
                        creators.append(path)
                    elif meta.tag == "PrecompiledHeader" and text == "NotUsing" and path.lower().endswith(".c"):
                        continue  # la génération fait de même pour les .c
                    elif meta.tag != "ExcludedFromBuild":
                        special.append(path)
    if special:
        notes[t(
            f"réglages propres à des fichiers non traduits : {', '.join(sorted(set(special)))}",
            f"per-file settings not translated: {', '.join(sorted(set(special)))}",
        )] = None
    return files, sorted(set(creators)), references


def _evaluate(
    xml: ElementTree.Element, configuration: str, platform: str, unevaluated: set[str]
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Les propriétés, et les métadonnées par outil, qui valent pour configuration|platform."""
    properties: dict[str, str] = {}
    tools: dict[str, dict[str, str]] = {}
    for group in xml:
        if group.tag not in ("PropertyGroup", "ItemDefinitionGroup") or not _applies(group, configuration, platform, unevaluated):
            continue
        for element in group:
            if not _applies(element, configuration, platform, unevaluated):
                continue
            if group.tag == "PropertyGroup":
                properties[element.tag] = (element.text or "").strip()
                continue
            metadata = tools.setdefault(element.tag, {})
            for meta in element:
                if _applies(meta, configuration, platform, unevaluated):
                    metadata[meta.tag] = (meta.text or "").strip()
    return properties, tools


def _applies(element: ElementTree.Element, configuration: str, platform: str, unevaluated: set[str]) -> bool:
    """La condition de l'élément vaut pour configuration|platform. Une autre forme de condition
    n'est pas évaluée : l'élément est écarté et la condition notée."""
    condition = element.get("Condition")
    if condition is None:
        return True
    match = _CONDITION.fullmatch(condition)
    if match is None:
        unevaluated.add(condition)
        return False
    return (match[1].lower(), match[2].lower()) == (configuration.lower(), platform.lower())


def _paths(value: str, root: Path, solution_dir: Path, here: Path, name: str, notes: dict[str, None]) -> list[str]:
    """Les chemins d'une liste du .vcxproj, relatifs à here, exprimés depuis root à barres obliques.
    Une macro inconnue ou un autre disque sont signalés."""
    macros = {
        "projectdir": f"{here}\\",
        "msbuildprojectdirectory": str(here),
        "msbuildthisfiledirectory": f"{here}\\",
        "solutiondir": f"{solution_dir}\\",
        "projectname": name,
    }
    paths = []
    for item in _split(value):
        text = _MACRO.sub(lambda match: macros.get(match[1].lower(), match[0]), item)
        try:
            relative = os.path.relpath(os.path.normpath(os.path.join(here, text)), root) if "$(" not in text else None
        except ValueError:
            relative = None
        if relative is None:
            notes[t(
                f"chemin {item} non traduit : macro inconnue ou autre disque",
                f"path {item} not translated: unknown macro or other drive",
            )] = None
        else:
            paths.append(relative.replace("\\", "/"))
    return paths


def _split(value: str) -> list[str]:
    """Les éléments d'une liste de MSBuild, séparés par ; puis déséchappés, sans l'héritage %(…)."""
    parts = [part.strip() for part in value.split(";")]
    return [_ESCAPE.sub(lambda match: chr(int(match[1], 16)), part) for part in parts if part and not part.startswith("%(")]


def _tokens(value: str) -> list[str]:
    """Les options d'un AdditionalOptions, sans l'héritage %(…)."""
    return [token for token in value.split() if not token.startswith("%(")]


def _section(text: str, name: str) -> str:
    match = re.search(rf"GlobalSection\({name}\)[^\n]*\n(.*?)EndGlobalSection", text, re.DOTALL)
    return match[1] if match else ""


def _relative(root: Path, path: Path) -> str:
    return os.path.relpath(path, root).replace("\\", "/")
