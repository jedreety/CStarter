"""VS Code : Code.exe, à côté de la commande code du PATH, sinon là où son installeur le met, pour
l'utilisateur seul ou pour la machine. Il ouvre le dossier d'un projet.
"""

import os
import shutil
import subprocess
from pathlib import Path

from cstarter.errors import ToolchainError
from cstarter.language import t


def find_vscode() -> Path:
    """Code.exe."""
    command = shutil.which("code")  # bin\code.cmd, dont Code.exe est le voisin du dossier parent
    candidates = [Path(command).parent.parent / "Code.exe"] if command else []
    for variable, *parts in (("LOCALAPPDATA", "Programs"), ("ProgramFiles",)):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable], *parts, "Microsoft VS Code", "Code.exe"))
    found = next((path for path in candidates if path.is_file()), None)
    if found is None:
        raise ToolchainError(
            t(
                "VS Code introuvable : installez-le (winget install --id Microsoft.VisualStudioCode --exact)",
                "VS Code not found: install it (winget install --id Microsoft.VisualStudioCode --exact)",
            )
        )
    return found


def open_folder(folder: Path) -> None:
    """Ouvre folder dans VS Code, sans l'attendre. ELECTRON_RUN_AS_NODE, hérité d'un processus que
    VS Code a lancé, ferait démarrer Code.exe comme Node, sans fenêtre : il ne passe pas."""
    environment = {name: value for name, value in os.environ.items() if name != "ELECTRON_RUN_AS_NODE"}
    subprocess.Popen(
        [str(find_vscode()), str(folder)],
        env=environment,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
