"""Les générations comparées.

Copie chaque projet d'exemples/ dans DOSSIER, hors du dépôt, puis le génère par la
ligne de commande : generate s'il a un .cstarter/ ; detect puis generate s'il a une
configuration à importer (CMakeLists.txt, premake5.lua, .sln, vcpkg.json,
conanfile.txt), en répondant oui à tout, puisque c'est une copie ; create sinon. Les
types que proposent les sources seules sont gardés, par create comme par detect quand
il n'y a que vcpkg.json ou conanfile.txt. Génère ensuite une seconde fois et signale
tout octet qui change. Un exemple qui ne se génère pas est signalé, et les autres continuent :
dependances exige ses entrées dans le cache, les imports exigent CMake, premake5,
vcpkg ou conan (README).

    .venv/Scripts/python scripts/generations.py DOSSIER/avant
    (modifier le code)
    .venv/Scripts/python scripts/generations.py DOSSIER/apres
    git diff --no-index DOSSIER/avant DOSSIER/apres
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cstarter import api  # après sys.path : pour compter les targets que detect fera confirmer

IMPORTS = ("CMakeLists.txt", "premake5.lua", "vcpkg.json", "conanfile.txt")
BUILDS = ("CMakeLists.txt", "premake5.lua")  # avec un .sln : des targets sans type à confirmer


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    out = Path(argv[0]).resolve()
    if out.exists() or out.is_relative_to(REPO):
        print(f"{out} : il faut un dossier qui n'existe pas encore, hors du dépôt")
        return 2
    unstable = []
    failed = []
    for example in sorted(path for path in (REPO / "exemples").iterdir() if path.is_dir()):
        copy = out / example.name
        shutil.copytree(example, copy)
        try:
            if (copy / ".cstarter").is_dir():
                _cstarter("-p", str(copy), "generate")
            elif any((copy / name).is_file() for name in IMPORTS) or any(copy.glob("*.sln")):
                built = any((copy / name).is_file() for name in BUILDS) or any(copy.glob("*.sln"))
                types = "" if built else "\n" * len(api.detect_sources(copy).targets)  # Entrée garde le type
                _cstarter("detect", "--location", str(copy), answers=types + "o\n" * 5)
                _cstarter("-p", str(copy), "generate")
            else:
                _cstarter("create", "--location", str(copy))
        except subprocess.CalledProcessError:
            failed.append(example.name)
            continue
        first = _snapshot(copy)
        _cstarter("-p", str(copy), "generate")
        if _snapshot(copy) != first:
            unstable.append(example.name)
    for name in failed:
        print(f"{name} : la génération a échoué, l'erreur est plus haut")
    for name in unstable:
        print(f"{name} : la seconde génération diffère de la première")
    return 1 if unstable or failed else 0


def _cstarter(*args: str, answers: str | None = None) -> None:
    """Lance la ligne de commande, avec answers pour ses questions. Sans elles, l'entrée fermée
    garde les réponses proposées."""
    if answers is None:
        subprocess.run([sys.executable, "-m", "cstarter", *args], cwd=REPO, stdin=subprocess.DEVNULL, check=True)
    else:
        subprocess.run([sys.executable, "-m", "cstarter", *args], cwd=REPO, input=answers, text=True, check=True)


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
