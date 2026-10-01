"""Le générateur Visual Studio 2022.

Il produit le .sln, puis pour chaque target le .vcxproj, le .vcxproj.filters et le
.vcxproj.user. Il lit le modèle, les entrées du cache résolues et la liste des
sources, jamais l'horloge ni le hasard, et n'écrit rien : il renvoie les fichiers,
en UTF-8 avec BOM et fins de ligne CRLF, comme Visual Studio les écrit. vs2026 le
reprend avec sa propre version de Visual Studio.
"""

import posixpath
import uuid
from dataclasses import dataclass
from xml.sax.saxutils import escape

from cstarter import config
from cstarter.errors import ConfigError
from cstarter.language import t


@dataclass(frozen=True)
class Version:
    """Ce qui distingue une version de Visual Studio dans les fichiers produits : son numéro,
    celui du .sln et de VCProjectVersion ; le build de sa première version, VisualStudioVersion du
    .sln ; son toolset."""

    major: int
    build: str
    toolset: str


# Visual Studio 2022, version 17.0.
VS2022 = Version(major=17, build="17.0.31903.59", toolset="v143")
TOOLSET = VS2022.toolset
MARK = "Généré par CStarter"
# Les extensions des fichiers produits : generate et clean y cherchent ceux que plus rien ne produit.
SUFFIXES = (".sln", ".vcxproj", ".vcxproj.filters", ".vcxproj.user")
_NOTICE = f"{MARK} depuis .cstarter/. Ne pas modifier : la génération suivante l'écrase."
_CPP_PROJECT_TYPE = "{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}"
_XMLNS = "http://schemas.microsoft.com/developer/msbuild/2003"
_PLATFORMS = config.MSVC_PLATFORMS
_CONFIGURATION_TYPES = {"executable": "Application", "static_lib": "StaticLibrary", "dynamic_lib": "DynamicLibrary"}
_SUBSYSTEMS = {"console": "Console", "windows": "Windows"}
_STANDARDS = {
    "c++14": "stdcpp14",
    "c++17": "stdcpp17",
    "c++20": "stdcpp20",
    "c++23": "stdcpp23",
    "c++latest": "stdcpplatest",
}
_C_STANDARDS = {"c11": "stdc11", "c17": "stdc17"}
_OPTIMIZATIONS = {"disabled": "Disabled", "min_size": "MinSpace", "max_speed": "MaxSpeed", "full": "Full"}
_RUNTIMES = config.MSVC_RUNTIMES
# Les caractères spéciaux de MSBuild, échappés pour rester littéraux.
_MSBUILD_ESCAPES = {"%": "%25", "$": "%24", "@": "%40", "'": "%27", ";": "%3B", "?": "%3F", "*": "%2A"}
_FNV_OFFSET = 0x6C62272E07BB014262B821756295C58D
_FNV_PRIME = 0x0000000001000000000000000000013B


def generate(
    project: config.Project, dependencies: dict[tuple[str, str], config.Dependency], version: Version = VS2022
) -> dict[str, bytes]:
    """Les fichiers de la solution : chemin relatif à la racine du projet, contenu.

    dependencies contient, par (nom, version), les entrées du cache que les targets lient.
    Ce qui est lié est vérifié avant de produire quoi que ce soit : runtimes, plateformes, et
    jamais deux entrées de la même source.
    """
    matrix = config.build_matrix(project)
    for target in project.targets.values():
        for c in target.configurations:
            config.check_dependencies(target, c, project.solution.platforms, _entries(target, c, dependencies))
    files = {_sln_path(project): _sln(project, matrix, version)}
    for target in project.targets.values():
        sources = config.resolve_sources(project.root, target)
        if target.pch is not None and target.pch.source not in sources:
            raise ConfigError(
                t(
                    f"{target.name} : pch.source {target.pch.source} ne fait pas partie de ses sources",
                    f"{target.name}: pch.source {target.pch.source} is not one of its sources",
                )
            )
        definitions = [f for f in sources if f.lower().endswith(config.DEFINITIONS)]
        if len(definitions) > 1:
            raise ConfigError(
                t(
                    f"{target.name} : plusieurs fichiers .def, l'éditeur de liens n'en prend qu'un : {', '.join(definitions)}",
                    f"{target.name}: several .def files, the linker takes only one: {', '.join(definitions)}",
                )
            )
        path = _vcxproj_path(target)
        files[path] = _vcxproj(project, target, sources, dependencies, version)
        files[path + ".filters"] = _filters(target, sources)
        files[path + ".user"] = _user(target)
    return files


def _sln(project: config.Project, matrix: dict[str, dict[str, str | None]], version: Version) -> bytes:
    here = project.solution.sln_output
    targets = _sln_order(project)
    platforms = project.solution.platforms  # la première est celle que Visual Studio ouvre
    lines = [
        "",
        "Microsoft Visual Studio Solution File, Format Version 12.00",
        f"# Visual Studio Version {version.major}",
        f"# {_NOTICE}",
        f"VisualStudioVersion = {version.build}",
        "MinimumVisualStudioVersion = 10.0.40219.1",
    ]
    for target in targets:
        path = _windows(_relative(_vcxproj_path(target), here))
        lines += [f'Project("{_CPP_PROJECT_TYPE}") = "{target.name}", "{path}", "{_target_guid(target)}"', "EndProject"]
    lines += ["Global", "\tGlobalSection(SolutionConfigurationPlatforms) = preSolution"]
    lines += [f"\t\t{s}|{p} = {s}|{p}" for s in matrix for p in platforms]
    lines += ["\tEndGlobalSection", "\tGlobalSection(ProjectConfigurationPlatforms) = postSolution"]
    for target in targets:
        guid = _target_guid(target)
        for s, built in matrix.items():
            # Un target non construit dans S garde une configuration active valide, sans Build.0.
            active = built[target.name] or target.configurations[0].name
            for p in platforms:
                lines.append(f"\t\t{guid}.{s}|{p}.ActiveCfg = {active}|{_PLATFORMS[p]}")
                if built[target.name]:
                    lines.append(f"\t\t{guid}.{s}|{p}.Build.0 = {active}|{_PLATFORMS[p]}")
    lines += [
        "\tEndGlobalSection",
        "\tGlobalSection(SolutionProperties) = preSolution",
        "\t\tHideSolutionNode = FALSE",
        "\tEndGlobalSection",
        "\tGlobalSection(ExtensibilityGlobals) = postSolution",
        f"\t\tSolutionGuid = {_guid(_sln_path(project))}",
        "\tEndGlobalSection",
        "EndGlobal",
    ]
    return _encode(lines)


def _sln_order(project: config.Project) -> list[config.Target]:
    """Le target de démarrage d'abord, Visual Studio prend le premier, puis l'ordre alphabétique."""
    startup = project.solution.startup_target
    return sorted(project.targets.values(), key=lambda target: (target.name != startup, target.name))


def _vcxproj(
    project: config.Project,
    target: config.Target,
    sources: list[str],
    dependencies: dict[tuple[str, str], config.Dependency],
    version: Version,
) -> bytes:
    here = target.vcxproj_dir
    pairs = [(c, p) for c in target.configurations for p in project.solution.platforms]
    lines = _xml_head(f'<Project DefaultTargets="Build" xmlns="{_XMLNS}">')
    lines.append('  <ItemGroup Label="ProjectConfigurations">')
    for c, p in pairs:
        lines += [
            f'    <ProjectConfiguration Include="{c.name}|{_PLATFORMS[p]}">',
            f"      <Configuration>{c.name}</Configuration>",
            f"      <Platform>{_PLATFORMS[p]}</Platform>",
            "    </ProjectConfiguration>",
        ]
    lines += [
        "  </ItemGroup>",
        '  <PropertyGroup Label="Globals">',
        f"    <VCProjectVersion>{version.major}.0</VCProjectVersion>",
        "    <Keyword>Win32Proj</Keyword>",
        f"    <ProjectGuid>{_target_guid(target)}</ProjectGuid>",
        f"    <RootNamespace>{target.name}</RootNamespace>",
        "    <WindowsTargetPlatformVersion>10.0</WindowsTargetPlatformVersion>",
        "  </PropertyGroup>",
        r'  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.Default.props" />',
    ]
    for c, p in pairs:
        lines += [
            f'  <PropertyGroup Condition="{_condition(c, p)}" Label="Configuration">',
            f"    <ConfigurationType>{_CONFIGURATION_TYPES[target.type]}</ConfigurationType>",
            f"    <UseDebugLibraries>{_bool(c.runtime_library.endswith('d'))}</UseDebugLibraries>",
            f"    <PlatformToolset>{version.toolset}</PlatformToolset>",
            "  </PropertyGroup>",
        ]
    lines.append(r'  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.props" />')
    for c, p in pairs:
        lines += [
            f'  <PropertyGroup Condition="{_condition(c, p)}">',
            f"    <OutDir>{_folder(f'{target.output.bin_dir}/{p}/{c.name}', here)}</OutDir>",
            f"    <IntDir>{_folder(f'{target.output.obj_dir}/{p}/{c.name}', here)}</IntDir>",
            "  </PropertyGroup>",
        ]
    includes = _include_dirs(project, target)
    definition = next((f for f in sources if f.lower().endswith(config.DEFINITIONS)), None)
    for c, p in pairs:
        lines += _item_definitions(project, target, c, p, includes, _entries(target, c, dependencies), definition)
    lines += _source_items(target, sources)
    lines += _references(project, target)
    lines.append(r'  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.targets" />')
    lines += _dll_copy(project, target, dependencies)
    lines.append("</Project>")
    return _encode(lines)


def _item_definitions(
    project: config.Project,
    target: config.Target,
    c: config.Configuration,
    platform: str,
    includes: str,
    entries: list[config.Dependency],
    definition: str | None,
) -> list[str]:
    """Les réglages d'une configuration sur une plateforme, les entrées du cache qu'elle
    lie : leur include/, leur lib/<plateforme>/ et leurs libs, et le .def du target."""
    defines = {**project.solution.global_defines, **c.defines}  # ceux de la configuration l'emportent
    compiler = [
        f"      <Optimization>{_OPTIMIZATIONS[c.optimization]}</Optimization>",
        f"      <WarningLevel>{c.warning_level}</WarningLevel>",
        f"      <RuntimeLibrary>{_RUNTIMES[c.runtime_library]}</RuntimeLibrary>",
        f"      <DebugInformationFormat>{'ProgramDatabase' if c.debug_info else 'None'}</DebugInformationFormat>",
        f"      <WholeProgramOptimization>{_bool(c.whole_program_opt)}</WholeProgramOptimization>",
        f"      <FunctionLevelLinking>{_bool(c.function_level_linking)}</FunctionLevelLinking>",
        f"      <LanguageStandard>{_STANDARDS[target.standard]}</LanguageStandard>",
    ]
    if target.c_standard is not None:
        compiler.append(f"      <LanguageStandard_C>{_C_STANDARDS[target.c_standard]}</LanguageStandard_C>")
    if defines:
        listed = ";".join(_define(name, value) for name, value in sorted(defines.items()))
        compiler.append(f"      <PreprocessorDefinitions>{listed};%(PreprocessorDefinitions)</PreprocessorDefinitions>")
    dirs = ([includes] if includes else []) + [_package(project, target, entry) + r"\include" for entry in entries]
    if dirs:
        compiler.append(
            f"      <AdditionalIncludeDirectories>{';'.join(dirs)};%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>"
        )
    if target.pch is not None:
        compiler += [
            "      <PrecompiledHeader>Use</PrecompiledHeader>",
            f"      <PrecompiledHeaderFile>{_text(target.pch.header)}</PrecompiledHeaderFile>",
        ]
    if c.compiler_options:
        compiler.append(f"      <AdditionalOptions>{_xml(' '.join(c.compiler_options))} %(AdditionalOptions)</AdditionalOptions>")
    lines = [f'  <ItemDefinitionGroup Condition="{_condition(c, platform)}">', "    <ClCompile>", *compiler, "    </ClCompile>"]
    libraries = _libraries(project, target, entries, platform)
    if target.type == "static_lib":
        lines += [
            "    <Lib>",
            f"      <LinkTimeCodeGeneration>{_bool(c.link_time_code_gen)}</LinkTimeCodeGeneration>",
            *libraries,
        ]
        if c.linker_options:  # le bibliothécaire les reçoit : une .lib nommée entre dans la bibliothèque
            lines.append(f"      <AdditionalOptions>{_xml(' '.join(c.linker_options))} %(AdditionalOptions)</AdditionalOptions>")
        lines.append("    </Lib>")
    else:
        link = [f"      <SubSystem>{_SUBSYSTEMS[target.subsystem]}</SubSystem>"] if target.type == "executable" else []
        link += [
            f"      <GenerateDebugInformation>{_bool(c.debug_info)}</GenerateDebugInformation>",
            f"      <LinkTimeCodeGeneration>{'UseLinkTimeCodeGeneration' if c.link_time_code_gen else 'Default'}</LinkTimeCodeGeneration>",
            *libraries,
        ]
        if definition is not None:
            link.append(f"      <ModuleDefinitionFile>{_text(_windows(_relative(definition, target.vcxproj_dir)))}</ModuleDefinitionFile>")
        if c.linker_options:
            link.append(f"      <AdditionalOptions>{_xml(' '.join(c.linker_options))} %(AdditionalOptions)</AdditionalOptions>")
        lines += ["    <Link>", *link, "    </Link>"]
    lines.append("  </ItemDefinitionGroup>")
    return lines


def _define(name: str, value: config.Define) -> str:
    """Un define de PreprocessorDefinitions : valeur telle quelle, sauf la forme string."""
    if value is None:
        return _text(name)
    if isinstance(value, dict):
        text = value["string"].replace("\\", "\\\\").replace('"', '\\"')
        return _text(f'{name}="{text}"')
    return _text(f"{name}={value}")


def _include_dirs(project: config.Project, target: config.Target) -> str:
    """Les headers publics du target, ses include_dirs, puis les headers publics de ses dépendances."""
    dirs = [target.public_headers] if target.public_headers else []
    dirs += target.sources.include_dirs
    for link in _links(project, target):
        dependency = project.targets[link.target]
        if dependency.public_headers:
            dirs.append(dependency.public_headers)
    return ";".join(_text(_windows(_relative(d, target.vcxproj_dir))) for d in dict.fromkeys(dirs))


def _source_items(target: config.Target, sources: list[str]) -> list[str]:
    lines = []
    for kind, files in _by_kind(sources):
        lines.append("  <ItemGroup>")
        for f in files:
            path = _text(_windows(_relative(f, target.vcxproj_dir)))
            pch = _pch_use(target, f) if kind == "ClCompile" else None
            if pch:
                lines += [f'    <{kind} Include="{path}">', f"      <PrecompiledHeader>{pch}</PrecompiledHeader>", f"    </{kind}>"]
            else:
                lines.append(f'    <{kind} Include="{path}" />')
        lines.append("  </ItemGroup>")
    return lines


def _pch_use(target: config.Target, source: str) -> str | None:
    """Le .cpp de l'en-tête précompilé le crée ; un .c ne peut pas utiliser celui du C++."""
    if target.pch is None:
        return None
    if source == target.pch.source:
        return "Create"
    return "NotUsing" if source.lower().endswith(".c") else None


def _references(project: config.Project, target: config.Target) -> list[str]:
    links = _links(project, target)
    if not links:
        return []
    lines = ["  <ItemGroup>"]
    for link in links:
        dependency = project.targets[link.target]
        path = _text(_windows(_relative(_vcxproj_path(dependency), target.vcxproj_dir)))
        lines += [
            f'    <ProjectReference Include="{path}">',
            f"      <Project>{_target_guid(dependency)}</Project>",
            "    </ProjectReference>",
        ]
    lines.append("  </ItemGroup>")
    return lines


def _libraries(
    project: config.Project, target: config.Target, entries: list[config.Dependency], platform: str
) -> list[str]:
    """Le lib/<plateforme>/ et les libs des entrées compilées, pour l'éditeur de liens ou le
    bibliothécaire. Un header-only n'a que son include/."""
    compiled = [entry for entry in entries if entry.nature != "header_only"]
    if not compiled:
        return []
    dirs = ";".join(f"{_package(project, target, entry)}\\lib\\{platform}" for entry in compiled)
    lines = [f"      <AdditionalLibraryDirectories>{dirs};%(AdditionalLibraryDirectories)</AdditionalLibraryDirectories>"]
    libs = [_text(lib) for entry in compiled for lib in entry.libs]
    if libs:
        lines.append(f"      <AdditionalDependencies>{';'.join(libs)};%(AdditionalDependencies)</AdditionalDependencies>")
    return lines


def _dll_copy(
    project: config.Project, target: config.Target, dependencies: dict[tuple[str, str], config.Dependency]
) -> list[str]:
    """Une tâche MSBuild qui copie après chaque build les DLL des entrées dynamic_lib à côté de la
    sortie, depuis Visual Studio comme depuis la ligne de commande."""
    if target.type == "static_lib":
        return []
    items = [
        f'      <CStarterDll Include="{_package(project, target, entry)}\\bin\\{p}\\*.dll" Condition="{_condition(c, p)}" />'
        for c in target.configurations
        for p in project.solution.platforms
        for entry in _entries(target, c, dependencies)
        if entry.nature == "dynamic_lib"
    ]
    if not items:
        return []
    return [
        '  <Target Name="CStarterCopyDlls" AfterTargets="Build">',
        "    <ItemGroup>",
        *items,
        "    </ItemGroup>",
        '    <Copy SourceFiles="@(CStarterDll)" DestinationFolder="$(OutDir)" SkipUnchangedFiles="true" />',
        "  </Target>",
    ]


def _filters(target: config.Target, sources: list[str]) -> bytes:
    """L'arborescence des sources : un filtre par dossier, sous le dossier commun à toutes."""
    base = posixpath.commonpath([posixpath.dirname(f) for f in sources]) if sources else ""
    filter_of = {f: _windows(posixpath.dirname(_relative(f, base or "."))) for f in sources}
    names = set()
    for name in filter_of.values():
        parts = name.split("\\") if name else []
        names.update("\\".join(parts[:i]) for i in range(1, len(parts) + 1))
    lines = _xml_head(f'<Project ToolsVersion="4.0" xmlns="{_XMLNS}">')
    if names:
        lines.append("  <ItemGroup>")
        for name in sorted(names):
            lines += [
                f'    <Filter Include="{_text(name)}">',
                f"      <UniqueIdentifier>{_guid(name)}</UniqueIdentifier>",
                "    </Filter>",
            ]
        lines.append("  </ItemGroup>")
    for kind, files in _by_kind(sources):
        lines.append("  <ItemGroup>")
        for f in files:
            path = _text(_windows(_relative(f, target.vcxproj_dir)))
            if filter_of[f]:
                lines += [f'    <{kind} Include="{path}">', f"      <Filter>{_text(filter_of[f])}</Filter>", f"    </{kind}>"]
            else:
                lines.append(f'    <{kind} Include="{path}" />')
        lines.append("  </ItemGroup>")
    lines.append("</Project>")
    return _encode(lines)


def _user(target: config.Target) -> bytes:
    """Les réglages du débogueur, communs à toutes les configurations."""
    debugger = target.debugger
    working_dir = _relative(debugger.working_dir, target.vcxproj_dir)
    lines = _xml_head(f'<Project ToolsVersion="Current" xmlns="{_XMLNS}">')
    lines += [
        "  <PropertyGroup>",
        "    <LocalDebuggerWorkingDirectory>$(ProjectDir)"
        f"{'' if working_dir == '.' else _text(_windows(working_dir))}</LocalDebuggerWorkingDirectory>",
    ]
    if debugger.arguments:
        lines.append(f"    <LocalDebuggerCommandArguments>{_text(debugger.arguments)}</LocalDebuggerCommandArguments>")
    if debugger.environment:
        variables = [_text(f"{name}={value}") for name, value in sorted(debugger.environment.items())]
        variables[0] = "    <LocalDebuggerEnvironment>" + variables[0]
        variables[-1] += "</LocalDebuggerEnvironment>"
        lines += variables
    lines += ["    <DebuggerFlavor>WindowsLocalDebugger</DebuggerFlavor>", "  </PropertyGroup>", "</Project>"]
    return _encode(lines)


def _by_kind(sources: list[str]) -> list[tuple[str, list[str]]]:
    """ClCompile pour les sources compilées, ClInclude pour les headers, ResourceCompile pour les
    .rc, None pour le .def, que l'éditeur de liens reçoit à part. Sans groupe vide."""
    kinds = [
        ("ClCompile", [f for f in sources if f.lower().endswith(config.COMPILED)]),
        ("ClInclude", [f for f in sources if f.lower().endswith(config.HEADERS)]),
        ("ResourceCompile", [f for f in sources if f.lower().endswith(config.RESOURCES)]),
        ("None", [f for f in sources if f.lower().endswith(config.DEFINITIONS)]),
    ]
    return [(kind, files) for kind, files in kinds if files]


def _links(project: config.Project, target: config.Target) -> list[config.Link]:
    return sorted(project.solution.depends_on(target.name), key=lambda link: link.target)


def _entries(
    target: config.Target, c: config.Configuration, dependencies: dict[tuple[str, str], config.Dependency]
) -> list[config.Dependency]:
    """Les entrées du cache que la configuration c lie, dans l'ordre où elle les déclare."""
    return [dependencies[(ref.name, ref.version)] for ref in target.dependencies.get(c.name, [])]


def _package(project: config.Project, target: config.Target, entry: config.Dependency) -> str:
    """Le dossier de l'entrée : relatif au .vcxproj si elle est vendorée, sinon écrit par
    $(USERPROFILE). C'est le même sur toutes les machines. Nom et version, validés, n'ont
    aucun caractère à échapper."""
    if config.DependencyRef(name=entry.name, version=entry.version) in project.vendored:
        return _windows(_relative(f".cstarter/vendor/{entry.name}/{entry.version}", target.vcxproj_dir))
    return f"$(USERPROFILE)\\.cstarter\\packages\\{entry.name}\\{entry.version}"


def _sln_path(project: config.Project) -> str:
    return posixpath.normpath(f"{project.solution.sln_output}/{project.name}.sln")


def _vcxproj_path(target: config.Target) -> str:
    return posixpath.normpath(f"{target.vcxproj_dir}/{target.name}.vcxproj")


def _target_guid(target: config.Target) -> str:
    """Le GUID importé s'il y en a un, sinon celui qui dérive du nom."""
    return target.guid or _guid(target.name)


def _guid(text: str) -> str:
    """Le FNV-1a sur 128 bits de text, écrit comme un GUID."""
    value = _FNV_OFFSET
    for byte in text.encode("utf-8"):
        value = ((value ^ byte) * _FNV_PRIME) % (1 << 128)
    return "{" + str(uuid.UUID(int=value)).upper() + "}"


def _relative(path: str, start: str) -> str:
    """path, relatif à la racine du projet, exprimé depuis start, relatif lui aussi."""
    parts = [part for part in posixpath.normpath(path).split("/") if part != "."]
    base = [part for part in posixpath.normpath(start).split("/") if part != "."]
    common = 0
    while common < min(len(parts), len(base)) and parts[common] == base[common]:
        common += 1
    return "/".join([".."] * (len(base) - common) + parts[common:]) or "."


def _folder(path: str, start: str) -> str:
    return _text(_windows(_relative(path, start))) + "\\"


def _condition(c: config.Configuration, platform: str) -> str:
    return f"'$(Configuration)|$(Platform)'=='{c.name}|{_PLATFORMS[platform]}'"


def _windows(path: str) -> str:
    return path.replace("/", "\\")


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _xml(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _text(value: str) -> str:
    """value littéral dans un fichier MSBuild : échappé pour MSBuild, puis pour XML."""
    return _xml("".join(_MSBUILD_ESCAPES.get(char, char) for char in value))


def _xml_head(project: str) -> list[str]:
    return ['<?xml version="1.0" encoding="utf-8"?>', f"<!-- {_NOTICE} -->", project]


def _encode(lines: list[str]) -> bytes:
    return ("\r\n".join(lines) + "\r\n").encode("utf-8-sig")
