"""registry.json, l'index des entrées du cache.

Il ne fait pas foi : les dossiers de packages/ font foi. Chaque liste du cache les
parcourt, puis réécrit registry.json s'il manque ou s'il diverge. Installation et
suppression passent par cette liste.
"""

import json
import os
import tempfile
from pathlib import Path


def sync(cache: Path, found: list[tuple[str, str]]) -> None:
    """Réécrit cache/registry.json d'un coup s'il ne décrit pas found, les entrées (nom, version)."""
    path = cache / "registry.json"
    versions: dict[str, list[str]] = {}
    for name, version in sorted(found):
        versions.setdefault(name, []).append(version)
    packages = [{"name": name, "versions": listed} for name, listed in sorted(versions.items())]
    content = (json.dumps({"packages": packages}, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if (path.is_file() and path.read_bytes() == content) or (not found and not path.exists()):
        return
    cache.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=cache, prefix=".registry.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(content)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
