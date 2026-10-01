"""Le builder none : un header-only, dont les headers sont copiés.

Une option, include=DOSSIER : le dossier des headers dans la source, include par défaut.
"""

from pathlib import Path

from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import layout


def build(source: Path, work: Path, stage: Path, flags: list[str], platforms: list[str], runtime: str | None) -> None:
    """Remplit stage/include/. Rien n'est compilé : ni plateforme, ni runtime, ni toolset."""
    folder = layout.designations(flags, ("include",), "none").get("include", "include")
    headers = layout.inside(source, folder)
    if not headers.is_dir():
        raise PackageError(
            t(
                f"builder none : pas de dossier {folder} dans la source ; désignez-le par include=DOSSIER",
                f"none builder: no {folder} folder in the source; designate it with include=FOLDER",
            )
        )
    layout.copy_headers(headers, stage)
