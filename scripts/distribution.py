"""Construit l'installeur de CStarter, dans un dossier hors du dépôt :

    python scripts/distribution.py C:\\cstarter-dist

1. la page de l'interface : npm ci, puis npm run build, dans cstarter/gui/web ;
2. l'exécutable figé, par PyInstaller d'après scripts/distribution/cstarter.spec : DOSSIER/CStarter,
   avec THIRD-PARTY-NOTICES.txt, la licence de chaque composant d'autrui qu'il embarque ;
3. l'installeur, par Inno Setup d'après scripts/distribution/cstarter.iss :
   DOSSIER/CStarter-<version>-setup.exe ;
4. DOSSIER/latest.json : la version, le nom de l'installeur et son empreinte SHA-256.

--etape n'en fait qu'une partie : executable (1 et 2), installeur (3) ou empreinte (4). La
construction des versions publiées, .github/workflows/publication.yml, fait signer par SignPath
entre deux étapes, et passe --signe : les exécutables, le désinstalleur, puis l'installeur doivent
alors porter la signature d'un des PUBLISHERS de cstarter/api/distribution.py. L'étape
desinstalleur, entre 2 et 3, écrit le désinstalleur d'Inno Setup à signer :
DOSSIER/desinstalleur/uninst-*.exe. Sans signature, l'installeur ne sert qu'aux essais : une
version se publie par scripts/publication.py.
PyInstaller s'installe dans le venv (scripts/distribution/requirements.txt), Inno Setup par winget
(README).
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path, PurePath

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().with_suffix("")
sys.path.insert(0, str(ROOT))

import cstarter  # noqa: E402
from cstarter.api import distribution as release  # noqa: E402

STEPS = ("executable", "desinstalleur", "installeur", "empreinte")
_LICENSE = ("license", "licence", "copying", "notice")
# Ce qu'un paquet Python embarque d'autrui sans en fournir la licence : scripts/distribution/licences/.
_CARRIED = {"pywebview": "Microsoft.Web.WebView2"}
# Les licences de domaine public, qui ne demandent aucune mention.
_PUBLIC_DOMAIN = {"Unlicense", "CC0-1.0", "0BSD"}


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
    uninstaller = folder / "desinstalleur"
    iscc = [f"/DVersion={version}", f"/DSource={folder / 'CStarter'}", f"/O{folder}", "/Q"]
    steps = [args.etape] if args.etape else ["executable", "installeur", "empreinte"]

    if "executable" in steps:
        web = ROOT / "cstarter" / "gui" / "web"
        npm = _tool("npm", "Node.js (winget install --id OpenJS.NodeJS.LTS --exact)")
        _run([npm, "ci"], web)
        _run([npm, "run", "build"], web)
        work = folder / "pyinstaller"
        _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(folder), "--workpath", str(work), str(HERE / "cstarter.spec")], ROOT)
        shutil.rmtree(work)
        _notices(folder / "CStarter")
    if "desinstalleur" in steps:
        # Inno Setup écrit le désinstalleur dans uninstaller, puis s'arrête jusqu'à ce qu'il soit signé.
        shutil.rmtree(uninstaller, ignore_errors=True)
        uninstaller.mkdir()
        subprocess.run([_iscc(), *iscc, f"/DSignedUninstaller={uninstaller}", str(HERE / "cstarter.iss")], cwd=HERE, check=False)
        stubs = list(uninstaller.glob("uninst-*.e32"))
        if len(stubs) != 1:
            sys.exit(f"Inno Setup n'a pas écrit le désinstalleur à signer dans {uninstaller}")
        print(f"\nÀ signer : {stubs[0].rename(stubs[0].with_suffix('.exe'))}")
    if "installeur" in steps:
        if args.signe:
            stubs = list(uninstaller.glob("uninst-*.exe"))
            if len(stubs) != 1:
                sys.exit(f"--signe : pas de désinstalleur signé dans {uninstaller}, voir --etape desinstalleur")
            _check_signed(folder / "CStarter" / "cstarter.exe", folder / "CStarter" / "cstarterw.exe", stubs[0])
            stubs[0].rename(stubs[0].with_suffix(".e32"))
            iscc.append(f"/DSignedUninstaller={uninstaller}")
        _run([_iscc(), *iscc, str(HERE / "cstarter.iss")], HERE)
    if "empreinte" in steps:
        if args.signe:
            _check_signed(installer)
        latest = {"version": version, "installer": installer.name, "sha256": _sha256(installer)}
        (folder / "latest.json").write_text(json.dumps(latest, indent=2) + "\n", encoding="utf-8")
        print(f"\n{installer}\n{folder / 'latest.json'}")
        if not args.signe:
            print("Non signé : pour essai seulement. Une version se publie par scripts/publication.py.")
    return 0


def _notices(app: Path) -> None:
    """app/THIRD-PARTY-NOTICES.txt : la licence de chaque composant d'autrui que l'installeur livre.
    Python, le chargeur de PyInstaller, les paquets Python que les exécutables embarquent, les
    paquets npm de production de la page, et Inno Setup, dont vient le désinstalleur. Un composant
    sans licence trouvée arrête la construction : scripts/distribution/licences/ la fournit."""
    sections = [(f"Python {platform.python_version()}", [Path(sys.base_prefix, "LICENSE.txt")])]
    pyinstaller = metadata.distribution("pyinstaller")
    sections.append((f"PyInstaller {pyinstaller.version}, son chargeur dans cstarter.exe et cstarterw.exe", _license_files(pyinstaller)))
    for name in _bundled(app):
        distribution = metadata.distribution(name)
        files = _license_files(distribution) or [HERE / "licences" / f"{name}.txt"]
        sections.append((f"{name} {distribution.version}", files))
        if name in _CARRIED:
            sections.append((f"{_CARRIED[name]}, dans {name}", [HERE / "licences" / f"{_CARRIED[name]}.txt"]))
    web = ROOT / "cstarter" / "gui" / "web"
    lock = json.loads((web / "package-lock.json").read_text(encoding="utf-8"))
    for key, package in sorted(lock["packages"].items()):
        if not key.startswith("node_modules/") or package.get("dev"):
            continue
        folder = web / key
        if not folder.is_dir() and package.get("optional"):
            continue  # facultatif, pour une autre plateforme : npm ne l'a pas installé
        files = sorted(path for path in folder.iterdir() if path.is_file() and path.name.lower().startswith(_LICENSE))
        if not files and package.get("license") not in _PUBLIC_DOMAIN:
            sys.exit(f"{key} : aucun fichier de licence, et {package.get('license')} demande une mention")
        sections.append((f"{key.rpartition('node_modules/')[2]} {package['version']}, licence {package.get('license')}, dans la page", files))
    sections.append(("Inno Setup, dont viennent l'installeur et le désinstalleur", [Path(_iscc()).with_name("license.txt")]))

    lines = [
        "Composants tiers livrés avec CStarter, et leurs licences.",
        "Third-party components shipped with CStarter, and their licenses.",
        "CStarter lui-même est sous licence MIT : LICENSE.txt.",
    ]
    for title, files in sections:
        missing = [path for path in files if not path.is_file()]
        if missing:
            sys.exit(f"{title} : licence introuvable, {missing[0]}")
        lines += ["", "=" * 80, title, "=" * 80]
        lines += [path.read_text(encoding="utf-8", errors="replace").strip() + "\n" for path in files]
        if not files:
            lines.append("Domaine public : aucune mention n'est demandée.\n")
    with open(app / "THIRD-PARTY-NOTICES.txt", "w", encoding="utf-8", newline="\r\n") as file:
        file.write("\n".join(lines))


def _bundled(app: Path) -> list[str]:
    """Les paquets Python que les exécutables figés embarquent, d'après leurs modules et _internal."""
    from PyInstaller.archive.readers import CArchiveReader

    names = {path.name.split(".")[0] for path in (app / "_internal").iterdir()}
    for executable in ("cstarter.exe", "cstarterw.exe"):
        reader = CArchiveReader(str(app / executable))
        for name, entry in reader.toc.items():
            if entry[-1] == "z":  # l'archive des modules
                names |= {module.split(".")[0] for module in reader.open_embedded_archive(name).toc}
    owners = metadata.packages_distributions()
    return sorted({owner for name in names for owner in owners.get(name, [])}, key=str.lower)


def _license_files(distribution: metadata.Distribution) -> list[Path]:
    """Les fichiers de licence qu'une distribution installe, ceux des paquets qu'elle intègre compris."""
    names = (PurePath(str(file)) for file in distribution.files or [])
    return sorted(Path(distribution.locate_file(name)) for name in names if name.name.lower().startswith(_LICENSE) and name.suffix not in {".py", ".pyc"})


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
