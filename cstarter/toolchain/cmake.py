"""CMake : dans le PATH, puis parmi les composants de Visual Studio,
que vswhere.exe trouve sans supposer de chemin d'installation. Et son File API, pour lire un
projet CMake.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from cstarter.errors import ToolchainError
from cstarter.language import t
from cstarter.toolchain import vswhere

_COMPONENT = "Microsoft.VisualStudio.Component.VC.CMake.Project"
def _missing() -> str:
    return t(
        "installez CMake (winget install --id Kitware.CMake --exact) ou le composant CMake de Visual Studio",
        "install CMake (winget install --id Kitware.CMake --exact) or the CMake component of Visual Studio",
    )


def find_cmake() -> Path:
    """cmake.exe du PATH, sinon celui de la plus récente installation de Visual Studio qui l'a."""
    found = shutil.which("cmake")
    if found:
        return Path(found)
    component = vswhere.find([_COMPONENT], r"Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe")
    if component is None:
        raise ToolchainError(t(f"CMake introuvable : {_missing()}", f"CMake not found: {_missing()}"))
    return component


def run_cmake(arguments: list[str]) -> None:
    """Lance CMake avec arguments. Sa sortie va au terminal ; un échec lève ToolchainError."""
    code = subprocess.run([str(find_cmake()), *arguments], check=False).returncode
    if code != 0:
        raise ToolchainError(
            t(f"CMake a échoué, code {code} : cmake {' '.join(arguments[:2])}", f"CMake failed, code {code}: cmake {' '.join(arguments[:2])}")
        )


def file_api(source: Path, kinds: tuple[str, ...] = ("codemodel",), arguments: list[str] | None = None) -> dict[str, object]:
    """Configure source dans un dossier temporaire, avec Visual Studio 2022 en x64, arguments en
    plus, et une requête du File API en version 2 pour chacun de kinds : codemodel (CMake 3.14 et
    plus), cache. Renvoie les réponses JSON, par nom de fichier. La configuration exécute le code
    du projet : l'appelant a l'accord de l'utilisateur."""
    with tempfile.TemporaryDirectory(prefix="cstarter-cmake-") as build:
        query = Path(build, ".cmake", "api", "v1", "query", "client-cstarter", "query.json")
        query.parent.mkdir(parents=True)
        query.write_text(json.dumps({"requests": [{"kind": kind, "version": 2} for kind in kinds]}) + "\n", encoding="utf-8")
        run_cmake(["-S", str(source), "-B", build, "-G", "Visual Studio 17 2022", "-A", "x64", *(arguments or [])])
        reply = Path(build, ".cmake", "api", "v1", "reply")
        return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in reply.glob("*.json")}
