"""Les types du modèle : projet, solution, target, configuration.

Les dataclasses reprennent un à un les champs des JSON de .cstarter/. Les chemins
restent des chaînes relatives à la racine du projet, à barres obliques.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

GENERATORS = ("vs2022", "vs2026")
IMPORTED_FROM = ("manual", "auto", "cmake", "premake", "vcxproj")
PLATFORMS = ("x64", "x86", "ARM64")
# Leur nom pour MSBuild (Platform) et pour CMake (-A).
MSVC_PLATFORMS = {"x64": "x64", "x86": "Win32", "ARM64": "ARM64"}
TARGET_TYPES = ("executable", "static_lib", "dynamic_lib")
SUBSYSTEMS = ("console", "windows")
STANDARDS = ("c++14", "c++17", "c++20", "c++23", "c++latest")
C_STANDARDS = ("c11", "c17")
SOURCE_MODES = ("auto", "manual")
OPTIMIZATIONS = ("disabled", "min_size", "max_speed", "full")
WARNING_LEVELS = ("Level1", "Level2", "Level3", "Level4", "EnableAllWarnings")
RUNTIMES = ("MD", "MDd", "MT", "MTd")
# Leur nom pour MSBuild (RuntimeLibrary) et pour CMake (CMAKE_MSVC_RUNTIME_LIBRARY).
MSVC_RUNTIMES = {"MD": "MultiThreadedDLL", "MDd": "MultiThreadedDebugDLL", "MT": "MultiThreaded", "MTd": "MultiThreadedDebug"}
# Les valeurs de metadata.json.
NATURES = ("header_only", "static_lib", "dynamic_lib")
SOURCE_TYPES = ("github", "gitlab", "url", "local", "vcpkg", "conan", "local_project")
BUILD_SYSTEMS = ("cmake", "premake", "msbuild", "vcpkg", "conan", "manual", "none")

# Nom d'un projet, d'un target ou d'une entrée du cache : il devient un nom de fichier.
NAME = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?")

# Un define : None, une valeur brute, un nombre, ou {"string": "..."}.
type Define = None | str | int | float | dict[str, str]


@dataclass
class Configuration:
    """Une configuration de build d'un target."""

    name: str
    optimization: str
    warning_level: str
    runtime_library: str
    debug_info: bool
    defines: dict[str, Define]
    whole_program_opt: bool
    function_level_linking: bool
    link_time_code_gen: bool
    compiler_options: list[str]
    linker_options: list[str]


@dataclass
class Sources:
    mode: str
    dirs: list[str]
    files: list[str]
    include_dirs: list[str]
    exclude: list[str]


@dataclass
class Output:
    bin_dir: str
    obj_dir: str


@dataclass
class Debugger:
    """Les réglages du débogueur, écrits dans le .vcxproj.user."""

    working_dir: str
    arguments: str
    environment: dict[str, str]


@dataclass
class Pch:
    """L'en-tête précompilé : le nom que les sources incluent, et le .cpp qui le crée."""

    header: str
    source: str


@dataclass
class DependencyRef:
    """Une entrée du cache liée à une configuration."""

    name: str
    version: str


@dataclass
class DependencySource:
    """L'origine d'une entrée du cache. Les champs sans objet pour son type valent None.
    Pour une archive : sha256 son empreinte, tree_sha256 celle de son contenu extrait, qui ne change
    pas quand l'archive est recompressée. Pour vcpkg : port, baseline, et tag la version exacte du
    port. Pour conan : ref."""

    type: str
    url: str | None = None
    tag: str | None = None
    commit: str | None = None
    sha256: str | None = None
    tree_sha256: str | None = None
    port: str | None = None
    baseline: str | None = None
    ref: str | None = None
    original_path: str | None = None
    resolvable: bool = True


@dataclass
class DependencyBuild:
    """La recette d'une entrée du cache. runtime vaut None pour un header-only, toolset
    quand rien n'a été compilé par CStarter."""

    system: str
    flags: list[str]
    platforms: list[str]
    runtime: str | None
    toolset: str | None


@dataclass
class Dependency:
    """Une entrée du cache, telle que son metadata.json la décrit. Résolue, c'est ce que
    la génération reçoit."""

    name: str
    version: str
    nature: str
    source: DependencySource
    build: DependencyBuild
    libs: list[str]
    requires: list[str]
    created_at: str


@dataclass
class CMakeOption:
    """Un paramètre de CMake : une variable du cache après configuration, ou une option() lue dans le
    CMakeLists.txt. type est celui du cache (BOOL, STRING, PATH, FILEPATH), values les valeurs
    permises d'un STRING, et default vaut ON ou OFF pour un BOOL configuré."""

    name: str
    default: str
    description: str
    type: str = "BOOL"
    values: list[str] = field(default_factory=list)


@dataclass
class Branch:
    """Une branche d'un dépôt, et le commit où elle en est."""

    name: str
    commit: str


@dataclass
class Versions:
    """Ce que la source d'une dépendance propose d'installer. source est son type. Pour un
    dépôt GitHub ou GitLab : ses tags, du plus récent au plus ancien, latest le plus récent qui
    n'est pas une préversion, et ses branches, la principale d'abord. Pour un port vcpkg : sa
    version dans la baseline la plus récente."""

    source: str
    tags: list[str]
    latest: str | None
    branches: list[Branch]


@dataclass
class AnalysisReport:
    """Ce que l'analyse trouve dans une source, sans rien compiler. nature vaut
    "ambiguous" quand plusieurs sont possibles. folders donne chaque dossier de la source,
    relatif et à barres obliques, "." pour la racine, avec ce qu'il contient directement :
    "headers", "lib", "dll". L'interface y désigne ceux des builders manual et none."""

    source: DependencySource
    build_systems: list[str]
    nature: str
    cmake_options: list[CMakeOption]
    presets: list[str]
    suggested_system: str
    suggested_flags: list[str]
    notes: list[str]
    folders: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class RestoreReport:
    """Ce que restore a fait de chaque entrée liée, désignée par name@version. failed
    donne aussi l'erreur, warnings ce que l'utilisateur doit fournir."""

    rebuilt: list[str]
    present: list[str]
    vendored: list[str]
    failed: list[str]
    warnings: list[str]


@dataclass
class GitChange:
    """Un fichier que git status montre, son chemin relatif à la racine du dépôt. index et
    worktree sont ses états dans l'index et dans le dossier de travail, les lettres de git status :
    M modifié, A ajouté, D supprimé, R renommé, U en conflit, ? non suivi, . inchangé. original est
    l'ancien chemin d'un fichier renommé."""

    path: str
    index: str
    worktree: str
    conflicted: bool
    original: str | None = None


@dataclass
class GitStatus:
    """L'état du dépôt d'un projet : sa racine ; sa branche, None si HEAD est détachée, celle
    qu'elle suit et les commits d'avance et de retard sur elle ; une fusion en cours, qu'un commit
    valide en entier ; les fichiers qui ont changé."""

    root: Path
    branch: str | None
    upstream: str | None
    ahead: int
    behind: int
    merging: bool
    changes: list[GitChange]


@dataclass
class GitReport:
    """Ce que pull, merge ou switch laisse : les fichiers en conflit, ceux de .cstarter/
    d'abord ; sinon, ce qui a empêché de régénérer la solution (un .cstarter/ invalide, une entrée
    absente du cache), ou les fichiers générés écrits."""

    conflicts: list[str]
    problem: str | None
    written: list[str]


@dataclass
class Update:
    """Une version publiée de CStarter : son numéro, le nom de son installeur et
    l'empreinte SHA-256 qu'il doit avoir."""

    version: str
    installer: str
    sha256: str


@dataclass
class Prerequisite:
    """Un outil que CStarter lance : son nom, sa présence sur cette machine, et le paquet
    winget qui l'installe."""

    name: str
    present: bool
    package: str


@dataclass
class Program:
    """Ce que run lance : l'exécutable du target de démarrage, le dossier où il démarre, ses
    arguments, les variables d'environnement que son débogueur ajoute, et s'il est fenêtré."""

    target: str
    path: Path
    working_dir: Path
    arguments: list[str]
    environment: dict[str, str]
    windowed: bool


@dataclass
class Remote:
    """Un remote du dépôt : son nom et son adresse."""

    name: str
    url: str


@dataclass
class Commit:
    """Un commit de l'historique : son empreinte, son sujet, son auteur et sa date ISO 8601."""

    hash: str
    subject: str
    author: str
    date: str


@dataclass
class Target:
    """Une unité compilable : targets/<name>.json, puis un .vcxproj."""

    name: str
    type: str
    subsystem: str
    standard: str
    c_standard: str | None
    vcxproj_dir: str
    public_headers: str | None
    pch: Pch | None
    sources: Sources
    output: Output
    debugger: Debugger
    configurations: list[Configuration]
    dependencies: dict[str, list[DependencyRef]]
    guid: str | None = None


@dataclass
class Link:
    """Un lien vers une dépendance, et la traduction de configurations qu'il porte."""

    target: str
    config_mapping: dict[str, str]


@dataclass
class SolutionTarget:
    name: str
    depends_on: list[Link]


@dataclass
class Solution:
    """solution.json : l'orchestration des targets."""

    platforms: list[str]
    startup_target: str | None
    sln_output: str
    global_defines: dict[str, Define]
    targets: list[SolutionTarget]

    def depends_on(self, name: str) -> list[Link]:
        """Les liens du target name, vide s'il n'en a pas."""
        return next((entry.depends_on for entry in self.targets if entry.name == name), [])


@dataclass
class Project:
    """Un projet en mémoire : ses trois entités et sa racine sur disque. vendored liste les entrées
    de .cstarter/vendor/, triées par nom et version."""

    root: Path
    name: str
    version: str
    generator: str
    imported_from: str
    solution: Solution
    targets: dict[str, Target]
    vendored: list[DependencyRef]


@dataclass
class Requirement:
    """Une dépendance que vcpkg.json ou conanfile.txt déclare. L'import l'installe par la source
    vcpkg ou conan. Pour vcpkg, source.tag est la version exacte quand le manifeste la fixe, et
    minimum son version>= ; flags sont les options de conan."""

    source: DependencySource
    minimum: str | None
    flags: list[str]


@dataclass
class Detection:
    """Ce qu'un détecteur reconnaît : un modèle partiel, et ce qu'il n'a pas su traduire.

    imported_from dit d'où viennent les targets, None pour un détecteur qui n'en propose pas.
    name est le nom de projet que la source suggère. solution porte les plateformes, le démarrage,
    les defines globaux et les liens entre targets. requirements sont les dépendances à installer
    par vcpkg ou conan. pending est ce qui ne se lit qu'en exécutant le code du projet, avec
    l'accord de l'utilisateur. info se montre sans jamais entrer dans .cstarter/. files sont les
    anciens fichiers de configuration, relatifs au dossier, dont la suppression est proposée."""

    targets: list[Target]
    notes: list[str]
    imported_from: str | None = "auto"
    name: str | None = None
    solution: Solution | None = None
    requirements: list[Requirement] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


def default_configurations() -> list[Configuration]:
    """Debug, Release et Dist, celles que create propose."""
    return [
        Configuration(
            name="Debug",
            optimization="disabled",
            warning_level="Level4",
            runtime_library="MDd",
            debug_info=True,
            defines={"_DEBUG": None},
            whole_program_opt=False,
            function_level_linking=False,
            link_time_code_gen=False,
            compiler_options=[],
            linker_options=[],
        ),
        Configuration(
            name="Release",
            optimization="max_speed",
            warning_level="Level3",
            runtime_library="MD",
            debug_info=True,
            defines={"NDEBUG": None},
            whole_program_opt=True,
            function_level_linking=True,
            link_time_code_gen=False,
            compiler_options=[],
            linker_options=[],
        ),
        Configuration(
            name="Dist",
            optimization="full",
            warning_level="Level3",
            runtime_library="MT",
            debug_info=False,
            defines={"DIST_BUILD": None, "NDEBUG": None},
            whole_program_opt=True,
            function_level_linking=True,
            link_time_code_gen=True,
            compiler_options=[],
            linker_options=[],
        ),
    ]


def new_target(name: str, type: str, subsystem: str = "console") -> Target:
    """Un target aux réglages par défaut, avec ses sources et son débogueur dans le dossier name."""
    return Target(
        name=name,
        type=type,
        subsystem=subsystem,
        standard="c++20",
        c_standard=None,
        vcxproj_dir="build",
        public_headers=None,
        pch=None,
        sources=Sources(mode="auto", dirs=[name], files=[], include_dirs=[], exclude=[]),
        output=Output(bin_dir=f"build/bin/{name}", obj_dir=f"build/obj/{name}"),
        debugger=Debugger(working_dir=name, arguments="", environment={}),
        configurations=default_configurations(),
        dependencies={},
    )


def safe_name(text: str) -> str:
    """Un nom valide tiré de text, un nom de dossier par exemple."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text).strip(".-") or "projet"
