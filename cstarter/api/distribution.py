"""La distribution : l'exécutable figé et ses mises à jour.

Installé, CStarter est un dossier que PyInstaller a figé : cstarter.exe, la ligne de commande, et
cstarterw.exe, l'interface. Chaque version se publie sur GitHub Releases, avec son installeur et
latest.json. Une version plus récente se télécharge en HTTPS, empreinte vérifiée, puis son
installeur remplace CStarter sans fenêtre.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import cstarter
from cstarter import config
from cstarter.errors import CStarterError
from cstarter.language import t
from cstarter.packages import archive

VERSION = cstarter.__version__
# L'adresse des versions publiées. Vide, elle désactive les mises à jour.
RELEASES = "https://github.com/jedreety/CStarter/releases"
_NUMBER = re.compile(r"\d+\.\d+\.\d+")
_INSTALLER = re.compile(r"[\w.-]+\.exe")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def executable() -> Path | None:
    """cstarter.exe, la ligne de commande de ce CStarter installé, ou None s'il tourne depuis ses
    sources."""
    return Path(sys.executable).with_name("cstarter.exe") if getattr(sys, "frozen", False) else None


def update_disabled() -> str | None:
    """Pourquoi ce CStarter ne se met pas à jour, ou None s'il le peut."""
    if executable() is None:
        return t("CStarter tourne depuis ses sources : git le met à jour", "CStarter runs from its sources: git updates it")
    if not RELEASES:
        return t("aucune adresse de publication : les mises à jour sont désactivées", "no release address: updates are disabled")
    return None


def check_update() -> config.Update | None:
    """La version publiée, si elle est plus récente que celle-ci ; None sinon. Les mises à jour
    doivent être possibles (update_disabled)."""
    try:
        latest = json.loads(archive.read_text(f"{RELEASES}/latest/download/latest.json"))
        update = config.Update(version=latest["version"], installer=latest["installer"], sha256=latest["sha256"])
    except (ValueError, KeyError, TypeError):
        raise CStarterError(t("latest.json illisible", "unreadable latest.json")) from None
    fields = ((_NUMBER, update.version), (_INSTALLER, update.installer), (_SHA256, update.sha256))
    if not all(isinstance(value, str) and pattern.fullmatch(value) for pattern, value in fields):
        raise CStarterError(t("latest.json illisible", "unreadable latest.json"))
    return update if _key(update.version) > _key(VERSION) else None


def download_update(update: config.Update) -> Path:
    """L'installeur de update, téléchargé dans %LOCALAPPDATA%\\CStarter\\mises-a-jour\\ s'il n'y est
    pas encore, et dont l'empreinte est celle de latest.json. Ce dossier ne garde que lui."""
    folder = Path(os.environ.get("LOCALAPPDATA", Path.home()), "CStarter", "mises-a-jour")
    folder.mkdir(parents=True, exist_ok=True)
    installer = folder / update.installer
    if not installer.is_file() or _digest(installer) != update.sha256:
        partial = folder / f"{update.installer}.part"
        if archive.download(f"{RELEASES}/download/v{update.version}/{update.installer}", partial) != update.sha256:
            partial.unlink()
            raise CStarterError(
                t(
                    f"{update.installer} : empreinte différente de celle de latest.json, installeur refusé",
                    f"{update.installer}: hash differs from latest.json, installer refused",
                )
            )
        os.replace(partial, installer)
    for old in folder.iterdir():
        if old.is_file() and old != installer:
            old.unlink()
    return installer


def install_update(installer: Path, relaunch: bool = False, project: Path | None = None) -> None:
    """Lance installer sans fenêtre, détaché : CStarter doit se fermer aussitôt, et l'installeur
    ferme ce qui en reste avant de remplacer ses fichiers. Avec relaunch, il relance ensuite
    l'interface, sur project s'il est donné."""
    arguments = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/FORCECLOSEAPPLICATIONS"]
    if relaunch:
        arguments += ["/RELAUNCH=1", *([f"/PROJECT={project}"] if project is not None else [])]
    subprocess.Popen(arguments, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
