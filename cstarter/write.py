"""La seule écriture dans un projet.

Seule api/ l'appelle. Un fichier n'est écrit que si ses octets changent, et d'un
coup : un fichier temporaire voisin, puis un renommage. Avec une marque, un fichier
existant qui ne la porte pas n'est écrasé ou supprimé qu'avec la confirmation de
l'utilisateur.

Ne dépend de rien d'autre dans cstarter, sauf errors.py.
"""

import os
import shutil
import tempfile
from collections.abc import Collection, Iterable
from pathlib import Path

from cstarter.errors import CStarterError, UnmarkedFileError
from cstarter.language import t

_HEAD = 1024  # la marque se cherche en tête de fichier


def write_files(
    root: Path, files: dict[str, bytes], mark: bytes | None, confirmed: Collection[str] = ()
) -> list[str]:
    """Écrit files, chemins relatifs à root, et renvoie ceux qui ont changé.

    Avec mark, un fichier existant qui ne la porte pas n'est écrasé que s'il figure
    dans confirmed. Sinon rien n'est écrit, et UnmarkedFileError les nomme tous.
    """
    changed = {}
    for rel, content in sorted(files.items()):
        path = _inside(root, rel)
        old = path.read_bytes() if path.is_file() else None
        if old != content:
            changed[rel] = (path, old, content)
    refused = [
        rel
        for rel, (_, old, _) in changed.items()
        if old is not None and mark is not None and mark not in old[:_HEAD] and rel not in confirmed
    ]
    if refused:
        raise UnmarkedFileError(refused)
    for path, _, content in changed.values():
        _replace(path, content)
    return list(changed)


def remove_files(root: Path, paths: Iterable[str], mark: bytes | None) -> list[str]:
    """Supprime ceux de paths qui existent et portent mark, tous si mark est None."""
    removed = []
    for rel in sorted(paths):
        path = _inside(root, rel)
        if path.is_file() and (mark is None or mark in path.read_bytes()[:_HEAD]):
            path.unlink()
            removed.append(rel)
    return removed


def remove_dirs(root: Path, paths: Iterable[str]) -> list[str]:
    """Supprime ceux des dossiers de paths qui existent, avec leur contenu."""
    removed = []
    for rel in sorted(paths):
        path = _inside(root, rel)
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(rel)
    return removed


def copy_files(root: Path, source: Path, paths: Iterable[str]) -> list[str]:
    """Copie les fichiers paths de source aux mêmes chemins sous root, et les renvoie. Aucun n'est
    écrasé : si l'un d'eux existe déjà sous root, rien n'est copié."""
    paths = sorted(paths)
    present = [rel for rel in paths if _inside(root, rel).exists()]
    if present:
        raise CStarterError(t(f"déjà présents : {', '.join(present)}", f"already present: {', '.join(present)}"))
    for rel in paths:
        path = _inside(root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_inside(source, rel), path)
    return paths


def _inside(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise CStarterError(t(f"chemin hors du projet : {rel}", f"path outside the project: {rel}"))
    return path


def _replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(content)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
