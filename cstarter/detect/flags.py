"""La traduction des options de cl.exe et de link.exe en champs du modèle,
pour les détecteurs de solutions Visual Studio et de CMake.

Une option qui a un champ dans le modèle le remplit, une option qui n'en a pas reste libre.
Une option qui doublerait un champ sans le remplir, ou qui désigne un fichier, est signalée :
le modèle ne la reprend pas.
"""

import re

from cstarter import config
from cstarter.language import t

_OPTIMIZATIONS = {"Od": "disabled", "O1": "min_size", "O2": "max_speed", "Ox": "full"}
_STANDARDS = {
    "c++14": "c++14",
    "c++17": "c++17",
    "c++20": "c++20",
    "c++23": "c++23",
    "c++23preview": "c++23",
    "c++latest": "c++latest",
}
_C_STANDARDS = {"c11": "c11", "c17": "c17"}
_DEFINE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Celles que MSBuild lie déjà (CoreLibraryDependencies) : les reprendre n'ajouterait rien.
DEFAULT_LIBRARIES = {
    "kernel32.lib",
    "user32.lib",
    "gdi32.lib",
    "winspool.lib",
    "comdlg32.lib",
    "advapi32.lib",
    "shell32.lib",
    "ole32.lib",
    "oleaut32.lib",
    "uuid.lib",
    "odbc32.lib",
    "odbccp32.lib",
}


def define(text: str) -> tuple[str, config.Define] | None:
    """NOM ou NOM=VALEUR en define du modèle : une chaîne C entre guillemets devient
    {"string": ...}, le reste une valeur brute. None si NOM n'est pas un identifiant."""
    name, equal, value = text.partition("=")
    if not _DEFINE.fullmatch(name):
        return None
    if not equal:
        return name, None
    if len(value) >= 2 and value[0] == value[-1] == '"' and not re.search(r'["\\]', value[1:-1]):
        return name, {"string": value[1:-1]}
    return name, value


def compiler(tokens: list[str], configuration: config.Configuration, target: config.Target, where: str, notes: list[str]) -> None:
    """Applique à configuration, et aux standards de target, les options de cl.exe tokens."""
    for token in tokens:
        flag = token[1:] if token[:1] in ("/", "-") else ""
        found = define(flag[1:]) if flag.startswith("D") else None
        if flag in _OPTIMIZATIONS:
            configuration.optimization = _OPTIMIZATIONS[flag]
        elif flag in config.RUNTIMES:
            configuration.runtime_library = flag
        elif re.fullmatch(r"W[1-4]", flag):
            configuration.warning_level = f"Level{flag[1]}"
        elif flag == "Wall":
            configuration.warning_level = "EnableAllWarnings"
        elif flag in ("Zi", "ZI", "Z7"):
            configuration.debug_info = True
        elif flag in ("GL", "GL-"):
            configuration.whole_program_opt = flag == "GL"
        elif flag in ("Gy", "Gy-"):
            configuration.function_level_linking = flag == "Gy"
        elif flag.startswith("std:") and flag[4:] in _STANDARDS:
            target.standard = _STANDARDS[flag[4:]]
        elif flag.startswith("std:") and flag[4:] in _C_STANDARDS:
            target.c_standard = _C_STANDARDS[flag[4:]]
        elif found is not None:
            configuration.defines[found[0]] = found[1]
        elif flag == "EHsc":
            pass  # le défaut de MSBuild
        elif flag and not config.doubles_field(token):
            configuration.compiler_options.append(token)
        else:
            notes.append(t(f"{where} : option de compilation {token} non traduite", f"{where}: compile option {token} not translated"))
    if configuration.runtime_library.endswith("d"):
        # MSBuild active /RTC1 avec le runtime de débogage : le reprendre le doublerait.
        configuration.compiler_options = [option for option in configuration.compiler_options if option[1:] != "RTC1"]


def linker(tokens: list[str], configuration: config.Configuration, target: config.Target, where: str, notes: list[str]) -> None:
    """Applique à configuration, et au sous-système de target, les options de link.exe tokens."""
    for token in tokens:
        flag = token[1:].upper() if token[:1] in ("/", "-") else ""
        if flag in ("DEBUG", "DEBUG:FULL", "DEBUG:FASTLINK"):
            configuration.debug_info = True
        elif flag.startswith("LTCG"):
            configuration.link_time_code_gen = True
        elif flag.startswith("SUBSYSTEM:"):
            target.subsystem = "windows" if flag[10:].startswith("WINDOWS") else "console"
        elif flag.startswith(("MACHINE:", "INCREMENTAL")):
            pass  # la plateforme, et le défaut de MSBuild
        elif not flag and token.lower().endswith(".lib") and not re.search(r"[/\\:]", token):
            if token.lower() not in DEFAULT_LIBRARIES:
                configuration.linker_options.append(token)
        elif flag and not config.doubles_field(token, linker=True) and not flag.startswith(("LIBPATH:", "DEF:", "OUT:", "PDB:", "IMPLIB:")):
            configuration.linker_options.append(token)
        else:
            notes.append(t(f"{where} : option de link {token} non traduite", f"{where}: link option {token} not translated"))
