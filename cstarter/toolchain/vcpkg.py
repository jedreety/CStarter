"""vcpkg : dans le PATH, puis le composant de Visual Studio,
que vswhere.exe trouve sans supposer de chemin d'installation.
"""

import shutil
import subprocess
from pathlib import Path

from cstarter.errors import ToolchainError
from cstarter.language import t
from cstarter.toolchain import vswhere

_COMPONENT = "Microsoft.VisualStudio.Component.Vcpkg"
def _missing() -> str:
    return t(
        "installez le composant vcpkg de Visual Studio (Microsoft.VisualStudio.Component.Vcpkg)",
        "install the vcpkg component of Visual Studio (Microsoft.VisualStudio.Component.Vcpkg)",
    )


def find_vcpkg() -> Path:
    """vcpkg.exe du PATH, sinon celui de la plus récente installation de Visual Studio qui l'a."""
    found = shutil.which("vcpkg")
    if found:
        return Path(found)
    component = vswhere.find([_COMPONENT], r"VC\vcpkg\vcpkg.exe")
    if component is None:
        raise ToolchainError(t(f"vcpkg introuvable : {_missing()}", f"vcpkg not found: {_missing()}"))
    return component


def run_vcpkg(arguments: list[str]) -> None:
    """Lance vcpkg avec arguments. Sa sortie va au terminal ; un échec lève ToolchainError."""
    code = subprocess.run([str(find_vcpkg()), *arguments], check=False).returncode
    if code != 0:
        raise ToolchainError(t(f"vcpkg a échoué, code {code} : vcpkg {arguments[0]}", f"vcpkg failed, code {code}: vcpkg {arguments[0]}"))
