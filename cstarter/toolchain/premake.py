"""Premake 5 : premake5.exe du PATH, installé à part. Et la
solution qu'il produit, pour lire un projet Premake.
"""

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cstarter.errors import ToolchainError
from cstarter.language import t

def _missing() -> str:
    return t(
        "installez Premake 5 (winget install --id Premake.Premake.5.Beta --exact), puis ouvrez un nouveau terminal",
        "install Premake 5 (winget install --id Premake.Premake.5.Beta --exact), then open a new terminal",
    )


def find_premake() -> Path:
    """premake5.exe du PATH."""
    found = shutil.which("premake5")
    if found:
        return Path(found)
    raise ToolchainError(t(f"premake5 introuvable : {_missing()}", f"premake5 not found: {_missing()}"))


def run_premake(arguments: list[str], folder: Path) -> None:
    """Lance premake5 avec arguments, dans folder. Sa sortie va au terminal ; un échec lève
    ToolchainError."""
    code = subprocess.run([str(find_premake()), *arguments], cwd=folder, check=False).returncode
    if code != 0:
        raise ToolchainError(
            t(f"premake5 a échoué, code {code} : premake5 {' '.join(arguments)}", f"premake5 failed, code {code}: premake5 {' '.join(arguments)}")
        )


@contextmanager
def generated_solution(folder: Path) -> Iterator[Path]:
    """Copie folder, sans .git ni .vs (l'état de Visual Studio, lourd et parfois verrouillé), dans
    un dossier temporaire du même nom, y lance premake5 vs2022, puis donne la copie : ce que premake5
    écrit n'atteint jamais folder. premake5 exécute le code du projet : l'appelant a l'accord de
    l'utilisateur."""
    with tempfile.TemporaryDirectory(prefix="cstarter-premake-") as work:
        copy = Path(work) / folder.resolve().name
        shutil.copytree(folder, copy, ignore=shutil.ignore_patterns(".git", ".vs"), copy_function=shutil.copyfile)
        run_premake(["--file=premake5.lua", "vs2022"], copy)
        yield copy
