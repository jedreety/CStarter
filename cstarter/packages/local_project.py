"""La source local_project : un projet CStarter de la machine, dont
export-dep fait d'un target une entrée du cache.

Comme la source local, elle n'est pas reconstructible ailleurs : le chemin du projet, absolu,
reste dans le metadata.json du cache et n'entre jamais dans un projet. Elle n'est pas
copiée : le builder msbuild compile le target sur place, dans la solution que l'export vient
de générer, et seules ses sorties quittent le projet.
"""

from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t


def fetch(source: config.DependencySource, work: Path) -> tuple[Path, config.DependencySource]:
    """Renvoie le dossier du projet et la source."""
    if source.tag is not None:
        raise PackageError(t("source local_project : pas de tag", "local_project source: no tag"))
    folder = Path(source.original_path or "")
    if not folder.is_absolute() or not (folder / ".cstarter").is_dir():
        raise PackageError(t(f"projet CStarter introuvable : {folder}", f"CStarter project not found: {folder}"))
    return folder, config.DependencySource(type="local_project", original_path=str(folder), resolvable=False)
