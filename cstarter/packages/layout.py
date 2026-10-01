"""La disposition d'une entrée du cache, que les builders remplissent.

include/ pour les headers, communs à toutes les plateformes ; lib/<plateforme>/ pour
les .lib et leurs .pdb ; bin/<plateforme>/ pour les .dll et leurs .pdb. Les fichiers
sont copiés sans leurs attributs : une entrée se supprime sans lutter contre un
fichier en lecture seule.
"""

import shutil
from pathlib import Path

from cstarter.errors import PackageError
from cstarter.language import t


def designations(flags: list[str], allowed: tuple[str, ...], builder: str) -> dict[str, str]:
    """Les options CLÉ=VALEUR d'un builder, CLÉ parmi allowed : un dossier, un fichier, un nom."""
    found = {}
    for flag in flags:
        key, equal, value = flag.partition("=")
        if not equal or not value or key not in allowed:
            raise PackageError(
                t(
                    f"builder {builder} : option refusée « {flag} », CLÉ=VALEUR attendu, CLÉ parmi {', '.join(allowed)}",
                    f"{builder} builder: option “{flag}” refused, KEY=VALUE expected, KEY among {', '.join(allowed)}",
                )
            )
        found[key] = value
    return found


def inside(source: Path, folder: str) -> Path:
    """Le dossier folder de la source, qui ne doit pas en sortir."""
    path = (source / folder).resolve()
    if not path.is_relative_to(source.resolve()):
        raise PackageError(t(f"« {folder} » sort du dossier de la source", f"“{folder}” leaves the source folder"))
    return path


def copy_headers(folder: Path, stage: Path) -> None:
    """Copie folder dans include/, ou vérifie qu'il est identique à ce qu'une autre plateforme
    y a mis : une entrée n'a qu'un dossier include/."""
    target = stage / "include"
    if not target.exists():
        shutil.copytree(folder, target, copy_function=shutil.copyfile)
    elif not same_tree(folder, target):
        raise PackageError(
            t(
                "les headers diffèrent d'une plateforme à l'autre : une entrée n'a qu'un dossier include/",
                "the headers differ from one platform to another: an entry has a single include/ folder",
            )
        )


def copy_binaries(folder: Path, target: Path, suffix: str) -> None:
    """Copie dans target les fichiers suffix de folder, sans descendre, et le .pdb de même nom de chacun."""
    if not folder.is_dir():
        return
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() == suffix:
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target / path.name)
            pdb = path.with_suffix(".pdb")
            if pdb.is_file():
                shutil.copyfile(pdb, target / pdb.name)


def same_tree(first: Path, second: Path) -> bool:
    """Les deux dossiers ont les mêmes fichiers, aux mêmes octets. Un dossier absent est vide."""
    return _files(first) == _files(second)


def _files(folder: Path) -> dict[str, bytes]:
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
