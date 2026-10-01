"""La source url : une archive zip ou tar, téléchargée en HTTPS."""

from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import archive


def fetch(source: config.DependencySource, work: Path) -> tuple[Path, config.DependencySource]:
    """Télécharge et extrait dans work l'archive de source. Renvoie le dossier des sources et la
    source complétée des empreintes de l'archive et de son contenu."""
    if source.tag is not None:
        raise PackageError(t("source url : pas de tag, l'URL désigne l'archive", "url source: no tag, the URL names the archive"))
    url = source.url or ""
    folder, sha256, tree = archive.fetch(url, work, url, source.sha256, source.tree_sha256)
    return folder, config.DependencySource(type="url", url=source.url, sha256=sha256, tree_sha256=tree)
