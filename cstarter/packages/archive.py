"""Le téléchargement et l'extraction des archives.

HTTPS seulement, redirections comprises. L'empreinte SHA-256 se calcule pendant le
téléchargement, et celle du contenu extrait après : une archive recompressée au contenu
identique, comme GitHub en produit parfois, reste acceptée. Un jeton ne suit pas les
redirections, et n'apparaît dans aucun message. Tout chemin extrait reste sous le dossier
cible : tarfile avec filter="data", zipfile contrôlé entrée par entrée.
"""

import hashlib
import http.client
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from cstarter.errors import PackageError
from cstarter.language import t


def fetch(
    url: str, work: Path, label: str, sha256: str | None, tree_sha256: str | None, token: str | None = None
) -> tuple[Path, str, str]:
    """Télécharge et extrait dans work l'archive url. Renvoie le dossier des sources, l'empreinte de
    l'archive et celle de son contenu. Une empreinte notée doit se retrouver : celle de l'archive, ou à
    défaut celle du contenu. L'archive recompressée garde alors l'empreinte notée."""
    found = download(url, work / "archive", token)
    folder = extract(work / "archive", work / "source")
    tree = tree_digest(folder)
    if sha256 is not None and found != sha256 and tree != tree_sha256:
        changed = t(", et son contenu a changé", ", and its content changed") if tree_sha256 else ""
        raise PackageError(
            t(
                f"{label} : l'archive n'a plus l'empreinte notée ({sha256}){changed}",
                f"{label}: the archive no longer has the recorded hash ({sha256}){changed}",
            )
        )
    return folder, sha256 or found, tree


def tree_digest(folder: Path) -> str:
    """L'empreinte SHA-256 du contenu de folder : le chemin et les octets de chaque fichier, sans ce
    qui n'est qu'emballage (compression, dates, droits)."""
    digest = hashlib.sha256()
    for relative, path in sorted((path.relative_to(folder).as_posix(), path) for path in folder.rglob("*") if path.is_file()):
        digest.update(relative.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def download(url: str, path: Path, token: str | None = None) -> str:
    """Télécharge url dans path et renvoie son empreinte SHA-256."""
    digest = hashlib.sha256()
    try:
        with _open(url, token, None) as response, open(path, "wb") as file:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                file.write(chunk)
    except (OSError, http.client.HTTPException) as error:  # connexion coupée ou trop lente
        raise PackageError(t(f"{url} : téléchargement interrompu, {error}", f"{url}: download interrupted, {error}")) from None
    return digest.hexdigest()


def read_text(url: str, token: str | None = None, accept: str | None = None) -> str:
    """Le corps de la réponse à url, en texte."""
    try:
        with _open(url, token, accept) as response:
            return response.read().decode("utf-8")
    except (OSError, http.client.HTTPException) as error:  # connexion coupée ou trop lente
        raise PackageError(t(f"{url} : réponse interrompue, {error}", f"{url}: response interrupted, {error}")) from None


def extract(archive: Path, folder: Path) -> Path:
    """Extrait archive, zip ou tar, dans folder, qu'elle crée. Renvoie le dossier unique
    qu'elle contient, comme celles de GitHub, ou sinon folder."""
    folder.mkdir()
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    if not (folder / name).resolve().is_relative_to(folder.resolve()):
                        raise PackageError(
                            t(
                                f"archive refusée : {name} sortirait du dossier d'extraction",
                                f"archive refused: {name} would leave the extraction folder",
                            )
                        )
                bundle.extractall(folder)
        elif tarfile.is_tarfile(archive):
            with tarfile.open(archive) as bundle:
                bundle.extractall(folder, filter="data")
        elif _html(archive):
            raise PackageError(
                t("le lien mène à une page web, pas à une archive zip ou tar", "the link leads to a web page, not to a zip or tar archive")
            )
        else:
            raise PackageError(t("archive illisible : zip ou tar attendu", "unreadable archive: zip or tar expected"))
    except (tarfile.TarError, zipfile.BadZipFile) as error:
        raise PackageError(t(f"archive refusée : {error}", f"archive refused: {error}")) from None
    content = list(folder.iterdir())
    return content[0] if len(content) == 1 and content[0].is_dir() else folder


def _html(path: Path) -> bool:
    """Si le téléchargement est une page web : le lien d'un dépôt ou d'une page de publication, par
    exemple, plutôt que celui d'une archive."""
    with open(path, "rb") as file:
        head = file.read(512).lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html"))


def _open(url: str, token: str | None, accept: str | None) -> http.client.HTTPResponse:
    if not url.startswith("https://"):
        raise PackageError(t(f"téléchargement refusé, HTTPS attendu : {url}", f"download refused, HTTPS expected: {url}"))
    request = urllib.request.Request(url, headers={"User-Agent": "cstarter"})
    if accept:
        request.add_header("Accept", accept)
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as error:
        raise PackageError(t(f"{url} : HTTP {error.code} {error.reason}", f"{url}: HTTP {error.code} {error.reason}")) from None
    except urllib.error.URLError as error:
        raise PackageError(t(f"{url} : {error.reason}", f"{url}: {error.reason}")) from None
    if not response.url.startswith("https://"):
        response.close()
        raise PackageError(t(f"{url} : redirigé hors de HTTPS", f"{url}: redirected away from HTTPS"))
    return response
