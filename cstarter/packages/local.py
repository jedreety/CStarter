"""La source local : un dossier de la machine.

Elle n'est pas reconstructible ailleurs : son chemin d'origine, absolu, reste dans le
metadata.json du cache et n'entre jamais dans un projet. Le dossier est copié
avant l'analyse et le build : CStarter n'écrit jamais dans les fichiers de l'utilisateur.
"""

import shutil
from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t


def fetch(source: config.DependencySource, work: Path) -> tuple[Path, config.DependencySource]:
    """Copie dans work le dossier de source, sans .git ni .vs (l'état de Visual Studio, lourd et
    parfois verrouillé). Renvoie la copie et la source."""
    if source.tag is not None:
        raise PackageError(t("source local : pas de tag", "local source: no tag"))
    folder = Path(source.original_path or "")
    if not folder.is_absolute() or not folder.is_dir():
        raise PackageError(t(f"dossier introuvable : {folder}", f"folder not found: {folder}"))
    copy = work / "source"
    shutil.copytree(folder, copy, ignore=shutil.ignore_patterns(".git", ".vs"), copy_function=shutil.copyfile)
    return copy, config.DependencySource(type="local", original_path=str(folder), resolvable=False)
