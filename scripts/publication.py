"""Publie la version de cstarter/__init__.py, en vérifiant chaque étape. Relançable : il reprend là
où en est cette version.

    python scripts/publication.py

1. Sans tag v<version> : vérifie que les fichiers suivis sont propres, que main est poussée telle
   quelle et que la version dépasse la dernière publiée ; puis, après confirmation, pose le tag et
   le pousse. GitHub Actions construit alors l'exécutable puis l'installeur, que SignPath signe
   chacun après approbation (.github/workflows/publication.yml), et les dépose dans un brouillon.
2. Devant le brouillon : télécharge l'installeur et latest.json, vérifie leur version, leur nom,
   l'empreinte et la signature ; puis, après confirmation, publie la release.
3. Publiée : attend que l'adresse fixe de latest.json serve cette version, puis fait ce que fera un
   CStarter plus ancien, dans un dossier jetable : trouver la version, télécharger l'installeur, en
   vérifier l'empreinte et la signature.

Les confirmations se lisent sur l'entrée standard : echo o | python scripts/publication.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cstarter  # noqa: E402
from cstarter.api import distribution as release  # noqa: E402
from cstarter.errors import CStarterError  # noqa: E402
from cstarter.packages import archive  # noqa: E402

VERSION = cstarter.__version__
TAG = f"v{VERSION}"
INSTALLER = f"CStarter-{VERSION}-setup.exe"
REPOSITORY = release.RELEASES.removeprefix("https://github.com/").removesuffix("/releases")


def main() -> int:
    state = _release()
    if state is None:
        return _tag()
    if state["isDraft"]:
        if not _check_draft(state["assets"]):
            return 1
        if not _confirm(f"Publier CStarter {VERSION} ? Les CStarter installés la téléchargeront à leur lancement. [o/N] "):
            print("rien n'est publié")
            return 1
        _run(_gh(), "release", "edit", TAG, "--repo", REPOSITORY, "--draft=false", "--latest")
    return _check_published()


def _tag() -> int:
    """Étape 1 : les vérifications, puis le tag, qui lance la construction."""
    if _run("git", "ls-remote", "--tags", "origin", f"refs/tags/{TAG}"):
        print(f"{TAG} est poussé, sans release encore : la construction tourne ou a échoué, https://github.com/{REPOSITORY}/actions")
        return 1
    problems = []
    if _run("git", "status", "--porcelain", "--untracked-files=no"):
        problems.append("des fichiers suivis sont modifiés : committe-les ou annule-les")
    if _run("git", "rev-parse", "--abbrev-ref", "HEAD") != "main":
        problems.append("la branche courante n'est pas main")
    _run("git", "fetch", "--quiet", "origin")
    if _run("git", "rev-parse", "HEAD") != _run("git", "rev-parse", "origin/main"):
        problems.append("main n'est pas poussée telle quelle : git push, ou git pull")
    latest = _latest_published()
    if latest is not None and release._key(VERSION) <= release._key(latest):
        problems.append(f"la version {VERSION} ne dépasse pas la dernière publiée, {latest} : monte-la dans cstarter/__init__.py")
    if _run("git", "tag", "--list", TAG):
        problems.append(f"le tag {TAG} existe ici sans être poussé : git tag -d {TAG}")
    if problems:
        print("\n".join(problems))
        return 1
    commit = _run("git", "rev-parse", "--short", "HEAD")
    if not _confirm(f"Poser le tag {TAG} sur {commit} et le pousser, ce qui lance la construction ? [o/N] "):
        print("aucun tag posé")
        return 1
    _run("git", "tag", "--annotate", TAG, "--message", f"CStarter {VERSION}")
    _run("git", "push", "--quiet", "origin", TAG)
    print(f"La construction démarre : https://github.com/{REPOSITORY}/actions")
    print("Approuve dans SignPath ses deux demandes de signature : l'exécutable, puis l'installeur.")
    print("Quand le brouillon de release est prêt, relance : python scripts/publication.py")
    return 0


def _check_draft(assets: list[dict]) -> bool:
    """Étape 2 : l'installeur et latest.json du brouillon, tels qu'un CStarter installé les lira."""
    missing = {INSTALLER, "latest.json"} - {asset["name"] for asset in assets}
    if missing:
        print(f"le brouillon {TAG} n'a pas {', '.join(sorted(missing))}")
        return False
    with tempfile.TemporaryDirectory() as folder:
        _run(_gh(), "release", "download", TAG, "--repo", REPOSITORY, "--dir", folder, "--pattern", INSTALLER, "--pattern", "latest.json")
        latest = json.loads(Path(folder, "latest.json").read_text(encoding="utf-8"))
        installer = Path(folder, INSTALLER)
        signed_by = release.signer(installer)
        problems = []
        if latest.get("version") != VERSION:
            problems.append(f"latest.json annonce {latest.get('version')}, et non {VERSION}")
        if latest.get("installer") != INSTALLER:
            problems.append(f"latest.json nomme {latest.get('installer')}, et non {INSTALLER}")
        if latest.get("sha256") != release._digest(installer):
            problems.append(f"l'empreinte de {INSTALLER} n'est pas celle de latest.json")
        if release.PUBLISHERS and signed_by not in release.PUBLISHERS:
            problems.append(f"{INSTALLER} est signé par {signed_by or 'personne'}, et non par {', '.join(release.PUBLISHERS)}")
    if problems:
        print("\n".join(problems))
        return False
    print(f"Brouillon {TAG} vérifié : version, nom, empreinte, et signature de {signed_by}.")
    return True


def _check_published() -> int:
    """Étape 3 : ce que verra un CStarter installé. latest.json peut tarder une minute ou deux."""
    deadline = time.monotonic() + 600
    while True:
        try:
            served = json.loads(archive.read_text(f"{release.RELEASES}/latest/download/latest.json")).get("version")
        except (CStarterError, ValueError):
            served = None
        if served == VERSION:
            break
        if time.monotonic() > deadline:
            print(f"latest.json sert encore {served} après dix minutes : la release {TAG} est-elle la dernière ?")
            return 1
        time.sleep(15)
    with tempfile.TemporaryDirectory() as folder:
        os.environ["LOCALAPPDATA"] = folder
        release.VERSION = "0.0.0"  # un CStarter plus ancien que toute version
        update = release.check_update()
        if update is None or update.version != VERSION:
            print(f"un CStarter plus ancien trouve {update.version if update else 'rien'}, et non {VERSION}")
            return 1
        installer = release.download_update(update)  # empreinte et signature vérifiées
        print(f"Vérifié comme un CStarter plus ancien : {installer.name} trouvé, téléchargé, empreinte et signature correctes.")
    print(f"CStarter {VERSION} est publié : https://github.com/{REPOSITORY}/releases/tag/{TAG}")
    return 0


def _release() -> dict | None:
    """La release du tag, brouillon compris, ou None si elle n'existe pas."""
    result = subprocess.run([_gh(), "release", "view", TAG, "--repo", REPOSITORY, "--json", "isDraft,assets"], capture_output=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode == 0:
        return json.loads(result.stdout)
    if "not found" in result.stderr.lower():
        return None
    sys.exit(f"gh release view : {result.stderr.strip()}")


def _latest_published() -> str | None:
    """Le numéro de la dernière version publiée, ou None s'il n'y en a aucune."""
    result = subprocess.run([_gh(), "api", f"repos/{REPOSITORY}/releases/latest", "--jq", ".tag_name"], capture_output=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode == 0:
        return result.stdout.strip().removeprefix("v")
    if "404" in result.stderr:
        return None
    sys.exit(f"gh api : {result.stderr.strip()}")


def _run(*command: str) -> str:
    """La sortie de command, sans ses blancs autour ; arrête tout s'il échoue."""
    result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        sys.exit(f"échec de {Path(command[0]).name} {command[1]} : {result.stderr.strip()}")
    return result.stdout.strip()


def _gh() -> str:
    """gh.exe, GitHub CLI : dans le PATH, sinon là où son installeur le met."""
    found = shutil.which("gh") or next((str(path) for path in [Path(os.environ.get("ProgramFiles", ""), "GitHub CLI", "gh.exe")] if path.is_file()), None)
    if found is None:
        sys.exit("gh introuvable : winget install --id GitHub.cli --exact, puis gh auth login")
    return found


def _confirm(question: str) -> bool:
    try:
        answer = input(question)
    except EOFError:
        answer = ""
    return answer.strip().lower() in {"o", "oui", "y", "yes"}


if __name__ == "__main__":
    sys.exit(main())
