"""Le builder premake : premake5.lua produit une solution Visual Studio
2022, que le builder msbuild compile.

premake5 s'exécute dans la source, qui est une copie dans le dossier de travail. Les options
sont celles du builder msbuild. sln=FICHIER désigne la solution quand premake5 en produit
plusieurs.
"""

from pathlib import Path

from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import msbuild
from cstarter.toolchain.premake import run_premake


def build(source: Path, work: Path, stage: Path, flags: list[str], platforms: list[str], runtime: str | None) -> str:
    """Produit la solution, puis remplit stage par le builder msbuild. Renvoie son toolset."""
    if not (source / "premake5.lua").is_file():
        raise PackageError(
            t("builder premake : pas de premake5.lua à la racine de la source", "premake builder: no premake5.lua at the root of the source")
        )
    before = set(source.rglob("*.sln"))
    run_premake(["--file=premake5.lua", "vs2022"], source)
    produced = sorted(set(source.rglob("*.sln")) - before)
    if len(produced) == 1 and not any(flag.startswith("sln=") for flag in flags):
        flags = [*flags, f"sln={produced[0].relative_to(source).as_posix()}"]
    return msbuild.build(source, work, stage, flags, platforms, runtime)
