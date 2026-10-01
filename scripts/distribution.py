"""Construit l'installeur de CStarter, dans un dossier hors du dépôt :

    python scripts/distribution.py C:\\cstarter-dist

1. la page de l'interface : npm ci, puis npm run build, dans cstarter/gui/web ;
2. l'exécutable figé, par PyInstaller d'après scripts/distribution/cstarter.spec : DOSSIER/CStarter ;
3. l'installeur, par Inno Setup d'après scripts/distribution/cstarter.iss :
   DOSSIER/CStarter-<version>-setup.exe ;
4. DOSSIER/latest.json : la version, le nom de l'installeur et son empreinte SHA-256.

--etape n'en fait qu'une partie : executable (1 et 2), installeur (3) ou empreinte (4). La
construction des versions publiées, .github/workflows/publication.yml, fait signer par SignPath
entre deux étapes, et passe --signe : les exécutables, puis l'installeur, doivent alors porter la
signature d'un des PUBLISHERS de cstarter/api/distribution.py. Sans signature, l'installeur ne sert
qu'aux essais : une version se publie par scripts/publication.py.
PyInstaller s'installe dans le venv (scripts/distribution/requirements.txt), Inno Setup par winget
(README).
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().with_suffix("")
sys.path.insert(0, str(ROOT))

import cstarter  # noqa: E402
from cstarter.api import distribution as release  # noqa: E402

STEPS = ("executable", "installeur", "empreinte")


def main() -> int:
    parser = argparse.ArgumentParser(description="Construit l'installeur de CStarter et latest.json.")
    parser.add_argument("folder", type=Path, metavar="DOSSIER", help="dossier de sortie, hors du dépôt")
    parser.add_argument("--etape", choices=STEPS, help="une seule étape ; sans elle, toutes")
    parser.add_argument("--signe", action="store_true", help="exiger la signature d'un des PUBLISHERS")
    args = parser.parse_args()
    folder = args.folder.resolve()
    if folder.is_relative_to(ROOT):
        parser.error("le dossier de sortie doit être hors du dépôt")
    if args.signe and not release.PUBLISHERS:
        parser.error("--signe : PUBLISHERS est vide dans cstarter/api/distribution.py")
    folder.mkdir(parents=True, exist_ok=True)
    version = cstarter.__version__
    installer = folder / f"CStarter-{version}-setup.exe"
    steps = [args.etape] if args.etape else STEPS

    if "executable" in steps:
        web = ROOT / "cstarter" / "gui" / "web"
        npm = _tool("npm", "Node.js (winget install --id OpenJS.NodeJS.LTS --exact)")
        _run([npm, "ci"], web)
        _run([npm, "run", "build"], web)
        work = folder / "pyinstaller"
        _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(folder), "--workpath", str(work), str(HERE / "cstarter.spec")], ROOT)
        shutil.rmtree(work)
    if "installeur" in steps:
        if args.signe:
            _check_signed(folder / "CStarter" / "cstarter.exe", folder / "CStarter" / "cstarterw.exe")
        _run([_iscc(), f"/DVersion={version}", f"/DSource={folder / 'CStarter'}", f"/O{folder}", "/Q", str(HERE / "cstarter.iss")], HERE)
    if "empreinte" in steps:
        if args.signe:
            _check_signed(installer)
        latest = {"version": version, "installer": installer.name, "sha256": _sha256(installer)}
        (folder / "latest.json").write_text(json.dumps(latest, indent=2) + "\n", encoding="utf-8")
        print(f"\n{installer}\n{folder / 'latest.json'}")
        if not args.signe:
            print("Non signé : pour essai seulement. Une version se publie par scripts/publication.py.")
    return 0


def _check_signed(*paths: Path) -> None:
    """Arrête la construction si un de paths ne porte pas la signature d'un des PUBLISHERS."""
    for path in paths:
        name = release.signer(path)
        if name not in release.PUBLISHERS:
            sys.exit(f"{path} : signé par {name or 'personne'}, et non par {', '.join(release.PUBLISHERS)}")


def _run(command: list[str], folder: Path) -> None:
    print(f"\n> {' '.join(command)}", flush=True)
    code = subprocess.run(command, cwd=folder, check=False).returncode
    if code != 0:
        sys.exit(f"échec, code {code} : {Path(command[0]).name}")


def _tool(name: str, install: str) -> str:
    found = shutil.which(name)
    if found is None:
        sys.exit(f"{name} introuvable : installez {install}")
    return found


def _iscc() -> str:
    """ISCC.exe, le compilateur d'Inno Setup : dans le PATH, sinon là où son installeur le met."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
        Path(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
    ]
    found = shutil.which("iscc") or next((str(path) for path in candidates if path.is_file()), None)
    if found is None:
        sys.exit("ISCC introuvable : winget install --id JRSoftware.InnoSetup --exact --scope user")
    return found


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
