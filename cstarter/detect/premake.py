"""Le détecteur Premake.

premake5 vs2022 s'exécute dans une copie temporaire du dossier, puis le détecteur de solutions
lit la solution qu'il produit : aucun code Lua à maintenir. premake5 exécute premake5.lua :
sans l'accord de l'utilisateur, le fichier attend dans pending.
"""

from pathlib import Path

from cstarter import config
from cstarter.detect import vcxproj
from cstarter.errors import ToolchainError
from cstarter.language import t
from cstarter.toolchain.premake import generated_solution


def detect(folder: Path, execute: bool = False) -> config.Detection | None:
    """Le projet Premake de folder, ou None s'il n'a pas de premake5.lua à sa racine."""
    if not (folder / "premake5.lua").is_file():
        return None
    if not execute:
        pending = [t("premake5.lua : premake5 l'exécute pour produire la solution", "premake5.lua: premake5 runs it to produce the solution")]
        return config.Detection(targets=[], notes=[], imported_from="premake", pending=pending, files=["premake5.lua"])
    before = {path.relative_to(folder) for path in folder.rglob("*.sln")}
    try:
        with generated_solution(folder) as copy:
            produced = sorted(path for path in copy.rglob("*.sln") if path.relative_to(copy) not in before)
            if not produced:
                notes = [t("premake5.lua : premake5 n'a produit aucune solution", "premake5.lua: premake5 produced no solution")]
                return config.Detection(targets=[], notes=notes, imported_from="premake", files=["premake5.lua"])
            # Les chemins relatifs à la copie sont ceux du dossier : la copie en a la même disposition.
            found = vcxproj.read_solution(copy, produced[0])
    except ToolchainError as error:
        return config.Detection(targets=[], notes=[t(
            f"premake5.lua non lu : {error}",
            f"premake5.lua not read: {error}",
        )], imported_from="premake", files=["premake5.lua"])
    found.notes += [t(f"{path.name} : solution de plus, non lue", f"{path.name}: extra solution, not read") for path in produced[1:]]
    found.imported_from = "premake"
    found.files = ["premake5.lua"]
    return found
