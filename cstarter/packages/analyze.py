"""L'analyse d'une source : la télécharger, l'examiner, ne rien compiler.

Elle trouve les systèmes de build présents, la nature probable, les paramètres et les
presets de CMake, et suggère un build. Une recherche textuelle se trompe sur une
condition ou une macro : c'est une suggestion, que l'utilisateur confirme. Configurée,
une source CMake donne tous ses paramètres, ceux que cmake-gui montrerait ; sinon, ce
sont les option() de son CMakeLists.txt.
"""

import json
import os
import re
import tempfile
from pathlib import Path

from cstarter import config
from cstarter.errors import ToolchainError
from cstarter.language import t
from cstarter.packages import SOURCES
from cstarter.toolchain.cmake import file_api

_OPTION = re.compile(r'^[ \t]*option\s*\(\s*(\w+)\s+"([^"]*)"\s*([^\s)]*)\s*\)', re.MULTILINE | re.IGNORECASE)
_LIBRARY = re.compile(r"^[ \t]*add_library\s*\(\s*[^\s)]+\s+([^\s)]+)", re.MULTILINE | re.IGNORECASE)
_MINIMUM = re.compile(r"cmake_minimum_required\s*\(\s*VERSION\s+(\d+)\.(\d+)", re.IGNORECASE)
# Le type d'un add_library. Sans type, une bibliothèque est statique, sauf BUILD_SHARED_LIBS.
_KINDS = {"INTERFACE": "header_only", "SHARED": "dynamic_lib", "MODULE": "dynamic_lib", "STATIC": "static_lib"}
_NOT_BUILT = ("ALIAS", "IMPORTED", "OBJECT", "UNKNOWN")
# Les valeurs vraies d'un BOOL du cache de CMake.
_TRUE = ("1", "ON", "YES", "TRUE", "Y")
# L'aide que CMake donne à ce que trouvent find_program, find_file, find_path et find_library :
# des outils de la machine, pas des paramètres du projet.
_FOUND = "Path to a "
# Ce que les builders manual et none désignent dans une source, par l'extension de ses fichiers.
_DESIGNATED = (("headers", frozenset(config.HEADERS)), ("lib", frozenset({".lib"})), ("dll", frozenset({".dll"})))


def analyze(source: config.DependencySource) -> config.AnalysisReport:
    """Télécharge ou copie source dans un dossier temporaire, l'examine, puis l'efface."""
    with tempfile.TemporaryDirectory(prefix="cstarter-") as work:
        return examine(*SOURCES[source.type](source, Path(work)))


def examine(folder: Path, source: config.DependencySource, configure: bool = False) -> config.AnalysisReport:
    """Le rapport sur folder, les sources que source a récupérées. Les sources vcpkg et conan
    délèguent la construction : leur builder est suggéré, sans rien examiner. Avec configure, une
    source CMake est configurée pour lister ses paramètres : son code s'exécute, comme au build."""
    if source.type in ("vcpkg", "conan"):
        return config.AnalysisReport(
            source=source,
            build_systems=[source.type],
            nature="ambiguous",
            cmake_options=[],
            presets=[],
            suggested_system=source.type,
            suggested_flags=[],
            notes=[t(
                f"{source.type} construit le package : sa nature se lira dans l'entrée installée",
                f"{source.type} builds the package: its nature will be read from the installed entry",
            )],
        )
    notes: list[str] = []
    cmakelists = folder / "CMakeLists.txt"
    cmake = cmakelists.read_text(encoding="utf-8", errors="replace") if cmakelists.is_file() else ""
    found = {
        "cmake": cmakelists.is_file(),
        "premake": (folder / "premake5.lua").is_file(),
        "msbuild": any(folder.glob("*.sln")),
    }
    systems = [system for system, present in found.items() if present]
    nature = _cmake_nature(cmake) if found["cmake"] else _files_nature(folder)
    flags = []
    minimum = _MINIMUM.search(cmake)
    if minimum and (int(minimum[1]), int(minimum[2])) < (3, 5):
        flags.append("-DCMAKE_POLICY_VERSION_MINIMUM=3.5")
        notes.append(
            t(
                f"cmake_minimum_required {minimum[1]}.{minimum[2]} précède 3.5, que CMake 4 refuse",
                f"cmake_minimum_required {minimum[1]}.{minimum[2]} is older than 3.5, which CMake 4 refuses",
            )
        )
    if found["cmake"]:
        system = "cmake"
    elif found["premake"]:
        system = "premake"
    elif found["msbuild"]:
        system = "msbuild"
    elif nature == "header_only":
        system = "none"
    else:
        system = "manual"
    if system == "none" and not (folder / "include").is_dir():
        notes.append(
            t(
                "pas de dossier include/ : désignez celui des headers par include=DOSSIER",
                "no include/ folder: designate the headers folder with include=FOLDER",
            )
        )
    options = [
        config.CMakeOption(name=name, default=default or "OFF", description=description)
        for name, description, default in _OPTION.findall(cmake)
    ]
    configured = _configured(folder, flags, notes) if configure and found["cmake"] else None
    if configured is not None:
        options, nature = configured
    return config.AnalysisReport(
        source=source,
        build_systems=systems,
        nature=nature,
        cmake_options=options,
        presets=_presets(folder / "CMakePresets.json", notes),
        suggested_system=system,
        suggested_flags=flags,
        notes=notes,
        folders=_folders(folder),
    )


def _configured(folder: Path, flags: list[str], notes: list[str]) -> tuple[list[config.CMakeOption], str] | None:
    """folder configuré avec flags : les paramètres de son cache, et la nature de ses targets
    installés. Les paramètres ne sont ni avancés, ni internes, ni ceux de CMake (CMAKE_*), que le
    builder fixe, ni les outils trouvés sur la machine ; un BOOL vaut ON ou OFF. None si la
    configuration échoue : l'erreur devient une note."""
    try:
        replies = file_api(folder, ("cache", "codemodel"), flags)
    except ToolchainError as error:
        notes.append(
            t(
                f"CMake ne configure pas la source, ses paramètres viennent de ses option() : {error}",
                f"CMake does not configure the source, its parameters come from its option(): {error}",
            )
        )
        return None
    installed = {reply.get("type") for name, reply in replies.items() if name.startswith("target-") and reply.get("install")}
    if installed & {"SHARED_LIBRARY", "MODULE_LIBRARY"}:
        nature = "dynamic_lib"
    elif "STATIC_LIBRARY" in installed:
        nature = "static_lib"
    else:
        nature = "header_only"  # une bibliothèque INTERFACE n'est pas un target du codemodel
    entries = next((reply.get("entries", []) for name, reply in replies.items() if name.startswith("cache-v2")), [])
    options = []
    for entry in entries:
        kind, name, value = entry["type"], entry["name"], entry["value"]
        properties = {item["name"]: item["value"] for item in entry.get("properties", [])}
        description = properties.get("HELPSTRING", "")
        if kind not in ("BOOL", "STRING", "PATH", "FILEPATH") or properties.get("ADVANCED") == "1" or name.startswith("CMAKE_"):
            continue
        if kind in ("PATH", "FILEPATH") and description.startswith(_FOUND):
            continue
        if kind == "BOOL":
            value = "ON" if value.upper() in _TRUE else "OFF"
        values = properties["STRINGS"].split(";") if "STRINGS" in properties else []
        options.append(config.CMakeOption(name=name, default=value, description=description, type=kind, values=values))
    return options, nature


def _cmake_nature(cmake: str) -> str:
    """La nature que les add_library du CMakeLists.txt de premier niveau laissent attendre."""
    kinds = {_KINDS.get(kind.upper(), "static_lib") for kind in _LIBRARY.findall(cmake) if kind.upper() not in _NOT_BUILT}
    return kinds.pop() if len(kinds) == 1 else "ambiguous"


def _files_nature(folder: Path) -> str:
    """Sans système de build : des DLL, des .lib, ou des headers seuls. Des sources à compiler
    sans système pour les construire laissent la nature ambiguë."""
    files = [path.name.lower() for path in folder.rglob("*") if path.is_file()]
    if any(name.endswith(".dll") for name in files):
        return "dynamic_lib"
    if any(name.endswith(".lib") for name in files):
        return "static_lib"
    return "ambiguous" if any(name.endswith(config.COMPILED) for name in files) else "header_only"


def _folders(folder: Path) -> dict[str, list[str]]:
    """Chaque dossier de folder, relatif, et ce qu'il contient directement : des headers, des .lib,
    des .dll. Les dossiers dont le nom commence par un point, comme .git, n'y sont pas."""
    found = {}
    for current, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
        suffixes = {os.path.splitext(name)[1].lower() for name in filenames}
        found[Path(current).relative_to(folder).as_posix()] = [kind for kind, wanted in _DESIGNATED if suffixes & wanted]
    return found


def _presets(path: Path, notes: list[str]) -> list[str]:
    """Les noms des configurePresets de CMakePresets.json."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        notes.append(t("CMakePresets.json illisible", "unreadable CMakePresets.json"))
        return []
    presets = data.get("configurePresets", []) if isinstance(data, dict) else []
    return [preset["name"] for preset in presets if isinstance(preset, dict) and isinstance(preset.get("name"), str)]
