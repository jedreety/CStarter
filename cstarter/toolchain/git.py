"""git : git.exe du PATH, pour le détecteur git, qui ne fait que lire.

Les détecteurs ne peuvent dépendre que de config/ et de toolchain/ : ils ne passent pas
par vcs/. Rien ici n'écrit dans .git/.
"""

import shutil
import subprocess
from pathlib import Path

from cstarter.errors import ToolchainError
from cstarter.language import t


def find_git() -> Path:
    """git.exe du PATH."""
    found = shutil.which("git")
    if found:
        return Path(found)
    raise ToolchainError(
        t(
            "git introuvable : installez Git (winget install --id Git.Git --exact)",
            "git not found: install Git (winget install --id Git.Git --exact)",
        )
    )


def git_output(folder: Path, arguments: list[str]) -> str:
    """La sortie de git lancé avec arguments dans le dépôt folder. Un échec lève ToolchainError."""
    result = subprocess.run(
        [str(find_git()), "-C", str(folder), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise ToolchainError(t(f"git {arguments[0]} : {result.stderr.strip()}", f"git {arguments[0]}: {result.stderr.strip()}"))
    return result.stdout
