"""Le builder msbuild : une solution Visual Studio, compilée par MSBuild.

Options : sln=FICHIER, la solution, sinon la seule du dossier de la source ; target=NOM, le
projet compilé avec ceux dont il dépend, sinon toute la solution ; configuration=NOM, sinon
Debug pour un runtime de débogage et Release pour les autres ; include=DOSSIER, les headers.

Pour chaque plateforme, toutes les sorties vont dans un même dossier de travail, dont les
.lib, les .dll et leurs .pdb forment l'entrée. Le runtime de l'entrée et le toolset v143
sont imposés à tous les projets de la solution : metadata.json dit vrai.
"""

import re
from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import layout
from cstarter.toolchain.msbuild import build as compile_solution

_KEYS = ("sln", "target", "configuration", "include")
_TOOLSET = "v143"
# Le nom de x86 dans une solution varie : x86 dans celles de CStarter, Win32 dans d'autres.
_PLATFORMS = {"x64": ("x64",), "x86": ("x86", "Win32"), "ARM64": ("ARM64",)}
_RUNTIMES = config.MSVC_RUNTIMES
# Importé par Microsoft.Cpp.targets après les réglages des projets : il l'emporte sur eux.
_RUNTIME_PROPS = """<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemDefinitionGroup>
    <ClCompile>
      <RuntimeLibrary>{runtime}</RuntimeLibrary>
    </ClCompile>
  </ItemDefinitionGroup>
</Project>
"""


def build(source: Path, work: Path, stage: Path, flags: list[str], platforms: list[str], runtime: str | None) -> str:
    """Remplit stage pour chaque plateforme et renvoie le toolset imposé."""
    designated = layout.designations(flags, _KEYS, "msbuild")
    solution = _solution(source, designated.get("sln"))
    text = solution.read_text(encoding="utf-8-sig", errors="replace")
    configuration = designated.get("configuration") or ("Debug" if (runtime or "").endswith("d") else "Release")
    props = work / "cstarter-runtime.props"
    props.write_text(_RUNTIME_PROPS.format(runtime=_RUNTIMES[runtime or ""]), encoding="utf-8")
    arguments = [
        f"-p:PlatformToolset={_TOOLSET}",
        f"-p:ForceImportBeforeCppTargets={props}",
        # Le dossier de travail est sous %TEMP% à dessein : MSBuild n'a pas à le signaler (MSB8029).
        "-p:IgnoreWarnIntDirInTempDetected=true",
    ]
    if "target" in designated:
        # Le target d'un projet de solution remplace ces caractères de son nom par _.
        arguments.append("-t:" + re.sub(r"[%$@;.()']", "_", designated["target"]))
    for platform in platforms:
        out = work / f"out-{platform}"
        code = compile_solution(
            solution, configuration, _platform(text, configuration, platform), _TOOLSET, [*arguments, f"-p:OutDir={out}\\"]
        )
        if code != 0:
            raise PackageError(
                t(
                    f"builder msbuild : MSBuild a échoué, code {code} : {solution.name}, {configuration}|{platform}",
                    f"msbuild builder: MSBuild failed, code {code}: {solution.name}, {configuration}|{platform}",
                )
            )
        layout.copy_binaries(out, stage / "lib" / platform, ".lib")
        layout.copy_binaries(out, stage / "bin" / platform, ".dll")
    if "include" in designated:
        layout.copy_headers(layout.inside(source, designated["include"]), stage)
    return _TOOLSET


def _solution(source: Path, designated: str | None) -> Path:
    """La solution désignée par sln=, sinon la seule du dossier de la source."""
    if designated is not None:
        path = layout.inside(source, designated)
        if path.suffix.lower() != ".sln" or not path.is_file():
            raise PackageError(
                t(f"builder msbuild : pas de solution {designated} dans la source", f"msbuild builder: no solution {designated} in the source")
            )
        return path
    found = sorted(source.glob("*.sln"))
    if len(found) != 1:
        raise PackageError(
            t(
                f"builder msbuild : {len(found)} solutions dans la source ; désignez-la par sln=FICHIER",
                f"msbuild builder: {len(found)} solutions in the source; designate one with sln=FILE",
            )
        )
    return found[0]


def _platform(text: str, configuration: str, platform: str) -> str:
    """Le nom que la solution donne à platform, pour configuration."""
    for name in _PLATFORMS[platform]:
        if f"{configuration}|{name} = " in text:
            return name
    raise PackageError(
        t(
            f"builder msbuild : la solution n'a pas la configuration {configuration}|{platform}",
            f"msbuild builder: the solution lacks configuration {configuration}|{platform}",
        )
    )
