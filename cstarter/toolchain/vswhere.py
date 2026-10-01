"""vswhere.exe : l'installeur de Visual Studio le place à un endroit fixe.
Il trouve un composant dans Visual Studio comme dans les Build Tools, sans supposer de chemin
d'installation.
"""

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path


def find(requires: Sequence[str], pattern: str) -> Path | None:
    """Le premier fichier pattern de la plus récente installation qui a les composants requires, ou
    None si vswhere.exe ou le fichier manque."""
    found = _find("-latest", requires, pattern)
    return found[0] if found else None


def find_all(requires: Sequence[str], pattern: str) -> list[Path]:
    """Les fichiers pattern de toutes les installations qui ont les composants requires, de la plus
    récente à la plus ancienne. Vide si vswhere.exe manque."""
    return _find("-sort", requires, pattern)


def _find(selection: str, requires: Sequence[str], pattern: str) -> list[Path]:
    programs = os.environ.get("ProgramFiles(x86)")
    vswhere = Path(programs, "Microsoft Visual Studio", "Installer", "vswhere.exe") if programs else None
    if vswhere is None or not vswhere.is_file():
        return []
    result = subprocess.run(
        [str(vswhere), selection, "-products", "*", "-requires", *requires, "-find", pattern, "-utf8"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return [Path(line) for line in result.stdout.splitlines()] if result.returncode == 0 else []
