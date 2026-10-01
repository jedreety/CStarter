"""conan 2 : le programme conan du PATH, installé à part.

CStarter le lance, il ne l'importe jamais comme bibliothèque Python.
"""

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from cstarter.errors import ToolchainError
from cstarter.language import t

def _missing() -> str:
    return t(
        "installez conan 2 (winget install --id JFrog.Conan --exact), puis ouvrez un nouveau terminal",
        "install conan 2 (winget install --id JFrog.Conan --exact), then open a new terminal",
    )


def find_conan() -> Path:
    """conan.exe du PATH."""
    found = shutil.which("conan")
    if found:
        return Path(found)
    raise ToolchainError(t(f"conan introuvable : {_missing()}", f"conan not found: {_missing()}"))


def run_conan(arguments: list[str], capture: bool = False, path: Sequence[Path] = ()) -> str:
    """Lance conan avec arguments. Sa sortie va au terminal, ou est renvoyée avec capture ; ses
    messages vont toujours au terminal. path met des dossiers en tête de son PATH, pour qu'il y
    trouve ses outils. Un échec lève ToolchainError."""
    environment = None
    if path:
        environment = {**os.environ, "PATH": os.pathsep.join([*map(str, path), os.environ.get("PATH", "")])}
    result = subprocess.run(
        [str(find_conan()), *arguments],
        stdout=subprocess.PIPE if capture else None,
        text=True,
        encoding="utf-8",
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise ToolchainError(
            t(f"conan a échoué, code {result.returncode} : conan {arguments[0]}", f"conan failed, code {result.returncode}: conan {arguments[0]}")
        )
    return result.stdout or ""
