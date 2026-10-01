"""Les prérequis : les outils que CStarter lance, cherchés comme il
les cherche, et installés par winget quand ils manquent.
"""

from collections.abc import Callable

from cstarter import config
from cstarter.errors import CStarterError, ToolchainError
from cstarter.generate import TOOLSETS
from cstarter.language import t
from cstarter.toolchain import cmake, conan, git, msbuild, premake, winget

# Visual Studio 2022 Community, avec la charge C++, les outils ARM64, CMake et vcpkg (README).
_VISUAL_STUDIO = (
    "--passive --wait --norestart --add Microsoft.VisualStudio.Workload.NativeDesktop --includeRecommended "
    "--add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.VC.Tools.ARM64 "
    "--add Microsoft.VisualStudio.Component.VC.CMake.Project --add Microsoft.VisualStudio.Component.Vcpkg"
)


def _visual_studio() -> None:
    """Le toolset C++ d'un générateur, pour x64."""
    if all(msbuild.missing_toolset(toolset, ["x64"]) for toolset in TOOLSETS.values()):
        raise ToolchainError(t("aucun toolset C++ de Visual Studio", "no Visual Studio C++ toolset"))


# Chaque prérequis, écrit en clair : son nom, ce qui le trouve et lève ToolchainError s'il
# manque, son paquet winget et les options de son installation.
_PREREQUISITES: tuple[tuple[str, Callable[[], object], str, tuple[str, ...]], ...] = (
    ("Visual Studio", _visual_studio, "Microsoft.VisualStudio.2022.Community", ("--override", _VISUAL_STUDIO)),
    ("git", git.find_git, "Git.Git", ()),
    ("CMake", cmake.find_cmake, "Kitware.CMake", ()),
    ("Premake", premake.find_premake, "Premake.Premake.5.Beta", ()),
    ("conan", conan.find_conan, "JFrog.Conan", ()),
)


def prerequisites() -> list[config.Prerequisite]:
    """Chaque prérequis, présent ou non sur cette machine, d'après le PATH de Windows : un outil
    installé depuis l'ouverture du terminal qui a lancé CStarter compte."""
    winget.refresh_path()
    return [config.Prerequisite(name=name, present=_present(find), package=package) for name, find, package, _ in _PREREQUISITES]


def install_prerequisite(name: str) -> None:
    """Installe le prérequis name par winget : sa sortie va au terminal, et Windows demande
    l'accord de l'administrateur quand l'installeur l'exige."""
    for known, _, package, options in _PREREQUISITES:
        if known == name:
            winget.install(package, options)
            return
    raise CStarterError(t(f"prérequis inconnu : {name}", f"unknown prerequisite: {name}"))


def _present(find: Callable[[], object]) -> bool:
    try:
        find()
    except ToolchainError:
        return False
    return True
