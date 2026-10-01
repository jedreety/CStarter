"""Les fichiers d'un target.

Mode auto : parcours récursif de dirs. Mode manual : motifs de files. Puis moins
exclude, triés. Seuls comptent les sources compilées, les headers, les ressources .rc
et les fichiers .def. Les dossiers dont le nom
commence par un point (.git, .vs, .cstarter) ne sont jamais parcourus.
"""

import os
import posixpath
from pathlib import Path, PurePosixPath

from cstarter.config.model import Target
from cstarter.errors import ConfigError
from cstarter.language import t

COMPILED = (".c", ".cpp", ".cc", ".cxx")
HEADERS = (".h", ".hpp", ".hxx", ".inl")
RESOURCES = (".rc",)
DEFINITIONS = (".def",)


def walk(root: Path, directory: str) -> list[str]:
    """Tous les fichiers sous directory, en chemins relatifs à root."""
    found = []
    for current, dirnames, filenames in os.walk(root / directory):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        here = _relative(root, current)
        found += [posixpath.normpath(posixpath.join(here, name)) for name in filenames]
    return found


def resolve_sources(root: Path, target: Target) -> list[str]:
    """Les sources compilées, les headers, les .rc et les .def du target, relatifs à root, triés."""
    sources = target.sources
    if sources.mode == "auto":
        found = []
        for directory in sources.dirs:
            if not (root / directory).is_dir():
                raise ConfigError(
                    t(f"{target.name} : dossier de sources introuvable : {directory}", f"{target.name}: source folder not found: {directory}")
                )
            found += walk(root, directory)
    else:
        found = [_relative(root, path) for pattern in sources.files for path in root.glob(pattern) if path.is_file()]
        found = [f for f in found if not any(part.startswith(".") and part != ".." for part in f.split("/")[:-1])]
    return sorted(
        {
            f
            for f in found
            if f.lower().endswith(COMPILED + HEADERS + RESOURCES + DEFINITIONS)
            and not any(PurePosixPath(f).full_match(pattern, case_sensitive=False) for pattern in sources.exclude)
        }
    )


def _relative(root: Path, path: str | Path) -> str:
    return posixpath.normpath(os.path.relpath(path, root).replace("\\", "/"))
