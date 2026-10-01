"""MSBuild, que vswhere.exe trouve dans Visual Studio comme dans les
Build Tools, pourvu que les outils C++ soient installés. Aucun chemin d'installation n'est
supposé. Chaque toolset, v143 ou v145, n'existe que dans les installations qui l'ont : celle
dont MSBuild compile est la plus récente qui l'a.
"""

import subprocess
from collections.abc import Sequence
from pathlib import Path

from cstarter.errors import ToolchainError
from cstarter.language import t
from cstarter.toolchain import vswhere

_REQUIRED = ("Microsoft.Component.MSBuild", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64")
# Les dossiers de Visual Studio nomment x86 comme MSBuild le fait dans un .vcxproj.
_FOLDERS = {"x86": "Win32"}


def find_msbuild(toolset: str, platform: str) -> Path:
    """MSBuild.exe de la plus récente installation qui a les outils C++ et toolset pour platform :
    x64, x86 ou ARM64."""
    installations = _installations(toolset, platform)
    if installations:
        for msbuild in vswhere.find_all(_REQUIRED, r"MSBuild\**\Bin\MSBuild.exe"):
            if msbuild.is_relative_to(installations[0]):
                return msbuild
    raise ToolchainError(
        t(
            f"MSBuild introuvable avec le toolset {toolset} pour {platform} : installez Visual Studio ou ses "
            f"Build Tools, avec la charge de travail Développement Desktop en C++ et les outils {toolset} de {platform}",
            f"MSBuild not found with toolset {toolset} for {platform}: install Visual Studio or its "
            f"Build Tools, with the Desktop development with C++ workload and the {toolset} tools for {platform}",
        )
    )


def missing_toolset(toolset: str, platforms: Sequence[str]) -> list[str]:
    """Celles de platforms pour lesquelles aucune installation n'a toolset."""
    return [platform for platform in platforms if not _installations(toolset, platform)]


def build(solution: Path, configuration: str, platform: str, toolset: str, arguments: Sequence[str] = ()) -> int:
    """Compile la solution avec le MSBuild qui a toolset, et renvoie son code de sortie. Sa sortie
    va au terminal. arguments s'ajoutent à la commande : un target, des propriétés."""
    command = [
        str(find_msbuild(toolset, platform)),
        str(solution),
        f"-p:Configuration={configuration}",
        f"-p:Platform={platform}",
        "-m",
        "-nologo",
        "-v:minimal",
        *arguments,
    ]
    return subprocess.run(command, check=False).returncode


def _installations(toolset: str, platform: str) -> list[Path]:
    """Les installations qui ont toolset pour platform, de la plus récente à la plus ancienne."""
    folder = _FOLDERS.get(platform, platform)
    pattern = rf"MSBuild\Microsoft\VC\*\Platforms\{folder}\PlatformToolsets\{toolset}\Toolset.props"
    # Toolset.props est à neuf niveaux sous le dossier de l'installation.
    return [found.parents[8] for found in vswhere.find_all(_REQUIRED, pattern)]
