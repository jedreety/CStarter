"""Le builder manual : l'utilisateur désigne, dans la source, les
headers, les bibliothèques et les DLL. Rien n'est compilé.

Options : include=DOSSIER, lib/PLATEFORME=DOSSIER, bin/PLATEFORME=DOSSIER. Les .lib
d'un dossier lib/, les .dll d'un dossier bin/, et leurs .pdb, sont copiés. Chaque
plateforme demandée a son dossier lib/. Les options peuvent désigner des plateformes
que l'on ajoutera plus tard à l'entrée.
"""

from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import layout

_KEYS = ("include", *(f"{kind}/{platform}" for kind in ("lib", "bin") for platform in config.PLATFORMS))


def build(source: Path, work: Path, stage: Path, flags: list[str], platforms: list[str], runtime: str | None) -> None:
    """Remplit stage de ce que les options désignent. Le toolset des binaires fournis est inconnu."""
    designated = layout.designations(flags, _KEYS, "manual")
    if "include" in designated:
        layout.copy_headers(layout.inside(source, designated["include"]), stage)
    for platform in platforms:
        if f"lib/{platform}" not in designated:
            raise PackageError(
                t(
                    f"builder manual : désignez les .lib de {platform} par lib/{platform}=DOSSIER",
                    f"manual builder: designate the .lib files of {platform} with lib/{platform}=FOLDER",
                )
            )
        for kind, suffix in (("lib", ".lib"), ("bin", ".dll")):
            if f"{kind}/{platform}" in designated:
                layout.copy_binaries(layout.inside(source, designated[f"{kind}/{platform}"]), stage / kind / platform, suffix)
