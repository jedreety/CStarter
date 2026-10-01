"""La distribution : l'exécutable figé et ses mises à jour.

Installé, CStarter est un dossier que PyInstaller a figé : cstarter.exe, la ligne de commande, et
cstarterw.exe, l'interface. Chaque version se publie sur GitHub Releases, avec son installeur et
latest.json. Une version plus récente se télécharge en HTTPS, empreinte et signature vérifiées,
puis son installeur, une fois que Windows accepte de le lancer, remplace CStarter sans fenêtre.
"""

import contextlib
import hashlib
import json
import os
import re
import shutil
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
# Les signataires admis pour un installeur, par une signature Authenticode valide. Vide, aucune
# signature n'est exigée : c'est le cas jusqu'à la première version que SignPath signe, qui y met
# "SignPath Foundation". Changer de signataire passe d'abord par une version qui admet les deux.
PUBLISHERS = ()
_NUMBER = re.compile(r"\d+\.\d+\.\d+")
_INSTALLER = re.compile(r"[\w.-]+\.exe")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SYSTEM32 = Path(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
# Le sujet du certificat qui signe le fichier de CSTARTER_SIGNED, si sa signature est valide.
_SUBJECT = "$s = Get-AuthenticodeSignature -LiteralPath $env:CSTARTER_SIGNED; if ($s.Status -eq 'Valid') { $s.SignerCertificate.Subject }"
_CN = re.compile(r'CN=(?:"([^"]*)"|([^,]*))')
_SUSPENDED = 0x00000004  # CREATE_SUSPENDED : le processus existe, rien de lui ne s'exécute
_BLOCKED = 4551  # une stratégie de contrôle des applications refuse le fichier : Smart App Control


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
    pas encore, dont l'empreinte est celle de latest.json et la signature celle d'un des
    PUBLISHERS. Ce dossier ne garde que lui."""
    folder = Path(os.environ.get("LOCALAPPDATA", Path.home()), "CStarter", "mises-a-jour")
    folder.mkdir(parents=True, exist_ok=True)
    installer = folder / update.installer
    if not installer.is_file() or _digest(installer) != update.sha256:
        # Un fichier partiel par processus : deux fenêtres ouvertes ensemble téléchargent chacune le sien.
        partial = folder / f"{update.installer}.{os.getpid()}.part"
        if archive.download(f"{RELEASES}/download/v{update.version}/{update.installer}", partial) != update.sha256:
            partial.unlink()
            raise CStarterError(
                t(
                    f"{update.installer} : empreinte différente de celle de latest.json, installeur refusé",
                    f"{update.installer}: hash differs from latest.json, installer refused",
                )
            )
        os.replace(partial, installer)
    _check_signature(installer)
    for old in folder.iterdir():
        if old.is_file() and old != installer:
            with contextlib.suppress(OSError):  # le partiel d'une autre fenêtre, encore ouvert
                old.unlink()
    return installer


def install_update(installer: Path, relaunch: bool = False, project: Path | None = None) -> None:
    """Lance installer sans fenêtre, détaché : CStarter doit se fermer aussitôt, et l'installeur
    ferme ce qui en reste avant de remplacer ses fichiers. Avec relaunch, il relance ensuite
    l'interface, sur project s'il est donné.

    Refusé quand une autre fenêtre de CStarter est ouverte : l'installeur la fermerait de force, avec
    ses modifications non enregistrées. relaunch vient de l'interface, qui compte sa propre fenêtre.
    La signature se vérifie encore : le fichier a pu changer depuis son téléchargement."""
    if _windows() > (1 if relaunch else 0):
        raise CStarterError(
            t("une autre fenêtre de CStarter est ouverte : fermez-la, puis recommencez", "another CStarter window is open: close it, then try again")
            if relaunch
            else t(
                "l'interface de CStarter est ouverte : fermez-la, ou mettez à jour depuis sa barre de titre",
                "the CStarter interface is open: close it, or update from its title bar",
            )
        )
    _check_signature(installer)
    arguments = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/FORCECLOSEAPPLICATIONS"]
    if relaunch:
        arguments += ["/RELAUNCH=1", *([f"/PROJECT={project}"] if project is not None else [])]
    try:
        subprocess.Popen(arguments, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    except OSError as error:
        if getattr(error, "winerror", None) != _BLOCKED:
            raise
        raise CStarterError(
            t(
                "Windows bloque encore cet installeur, qui n'est pas signé : Smart App Control l'acceptera une fois que Microsoft l'aura évalué. Réessayez plus tard.",
                "Windows still blocks this unsigned installer: Smart App Control will accept it once Microsoft has assessed it. Try again later.",
            )
        ) from None


def installer_allowed(installer: Path) -> bool:
    """Windows laisse-t-il lancer installer ? Smart App Control refuse un exécutable non signé tant
    que Microsoft ne l'a pas évalué, de quelques minutes à quelques heures après sa publication, et un
    refus peut rester attaché au fichier refusé. La question se pose donc sur une copie fraîche,
    lancée suspendue puis tuée : rien de l'installeur ne s'exécute. Acceptée, la copie le remplace."""
    probe = installer.with_name(f"{installer.stem}.{os.getpid()}.sonde{installer.suffix}")
    shutil.copyfile(installer, probe)
    try:
        process = subprocess.Popen([str(probe)], creationflags=_SUSPENDED | subprocess.CREATE_NO_WINDOW)
    except OSError as error:
        probe.unlink(missing_ok=True)
        if getattr(error, "winerror", None) != _BLOCKED:
            raise
        return False
    process.kill()
    process.wait()
    os.replace(probe, installer)
    return True


def update_waiting(version: str) -> str:
    """Pourquoi la version publiée ne s'installe pas encore : Windows refuse son installeur."""
    return t(
        f"Windows vérifie encore CStarter {version} : Smart App Control bloque une version non signée tant que Microsoft ne l'a pas évaluée, de quelques minutes à quelques heures après sa publication. Réessayez plus tard.",
        f"Windows is still checking CStarter {version}: Smart App Control blocks an unsigned release until Microsoft has assessed it, a few minutes to a few hours after it is published. Try again later.",
    )


def signer(path: Path) -> str | None:
    """Le nom de qui signe path, si sa signature Authenticode est valide ; None sinon."""
    result = subprocess.run(
        [str(_SYSTEM32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"), "-NoProfile", "-NonInteractive", "-Command", _SUBJECT],
        env={**os.environ, "CSTARTER_SIGNED": str(path)},
        capture_output=True,
        encoding="oem",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    match = _CN.search(result.stdout)
    if match is None:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2).strip()


def _check_signature(installer: Path) -> None:
    """Lève CStarterError si PUBLISHERS en nomme et qu'aucun ne signe installer."""
    if PUBLISHERS and signer(installer) not in PUBLISHERS:
        raise CStarterError(
            t(
                f"{installer.name} : aucune signature valide de {', '.join(PUBLISHERS)}, installeur refusé",
                f"{installer.name}: no valid signature from {', '.join(PUBLISHERS)}, installer refused",
            )
        )


def _windows() -> int:
    """Le nombre d'interfaces de CStarter ouvertes : les processus cstarterw.exe."""
    result = subprocess.run(
        [str(_SYSTEM32 / "tasklist.exe"), "/FI", "IMAGENAME eq cstarterw.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        encoding="oem",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    return sum(line.lower().startswith('"cstarterw.exe"') for line in result.stdout.splitlines())


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
