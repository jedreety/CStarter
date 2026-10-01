"""winget : le gestionnaire de paquets de Windows, qui installe les
prérequis. winget.exe du PATH, que Windows 11 fournit avec App Installer.
"""

import os
import shutil
import subprocess
import winreg
from collections.abc import Sequence

from cstarter.errors import ToolchainError
from cstarter.language import t

# Le PATH de Windows : celui de la machine, puis celui de l'utilisateur.
_ENVIRONMENTS = (
    (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    (winreg.HKEY_CURRENT_USER, "Environment"),
)


def install(package: str, options: Sequence[str] = ()) -> None:
    """Installe package, un identifiant winget, avec options. Sa sortie va au terminal ; Windows
    demande l'accord de l'administrateur (UAC) quand l'installeur l'exige. Le PATH du processus
    reprend ensuite ce que l'installation a ajouté à celui de Windows : l'outil se trouve sans
    relancer CStarter. Un échec lève ToolchainError."""
    found = shutil.which("winget")
    if found is None:
        raise ToolchainError(
            t(
                "winget introuvable : installez App Installer depuis le Microsoft Store",
                "winget not found: install App Installer from the Microsoft Store",
            )
        )
    command = [found, "install", "--id", package, "--exact", "--source", "winget"]
    command += ["--accept-package-agreements", "--accept-source-agreements", *options]
    code = subprocess.run(command, check=False).returncode
    if code != 0:
        raise ToolchainError(t(f"winget a échoué, code {code & 0xFFFFFFFF:#x} : {package}", f"winget failed, code {code & 0xFFFFFFFF:#x}: {package}"))
    refresh_path()


def refresh_path() -> None:
    """Ajoute au PATH du processus les dossiers du PATH de Windows qui lui manquent : un outil
    installé depuis le lancement de CStarter, ou du terminal qui l'a lancé, se trouve alors."""
    current = os.environ.get("PATH", "")
    known = {os.path.normcase(folder.rstrip("\\")) for folder in current.split(os.pathsep) if folder}
    added = []
    for root, key in _ENVIRONMENTS:
        try:
            with winreg.OpenKey(root, key) as handle:
                value = winreg.ExpandEnvironmentStrings(winreg.QueryValueEx(handle, "Path")[0])
        except OSError:
            continue
        for folder in value.split(os.pathsep):
            if folder and os.path.normcase(folder.rstrip("\\")) not in known:
                known.add(os.path.normcase(folder.rstrip("\\")))
                added.append(folder)
    if added:
        os.environ["PATH"] = os.pathsep.join([current, *added]) if current else os.pathsep.join(added)
