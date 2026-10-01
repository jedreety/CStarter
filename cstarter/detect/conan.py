"""Le détecteur conanfile.txt : les dépendances de conan.

Chaque ligne de [requires] devient une dépendance à installer par la source conan, avec les
lignes de [options] qui la concernent. Un intervalle de versions ne se traduit pas, les autres
sections non plus : ils sont signalés. Un conanfile.py est du Python : il est signalé, jamais
exécuté.
"""

import fnmatch
from pathlib import Path

from cstarter import config
from cstarter.language import t


def detect(folder: Path, execute: bool = False) -> config.Detection | None:
    """Les dépendances du conanfile.txt de folder, ou None s'il n'a ni conanfile.txt ni conanfile.py."""
    text_file, python_file = folder / "conanfile.txt", folder / "conanfile.py"
    if not text_file.is_file() and not python_file.is_file():
        return None
    notes, files, requirements = [], [], []
    if python_file.is_file():
        # Jamais lu : sa suppression n'est pas proposée.
        notes.append(
            t(
                "conanfile.py : du Python, jamais exécuté, ses dépendances ne sont pas lues",
                "conanfile.py: Python code, never run, its dependencies are not read",
            )
        )
    if text_file.is_file():
        files.append("conanfile.txt")
        sections = _sections(text_file.read_text(encoding="utf-8-sig", errors="replace"))
        notes += [t(
            f"conanfile.txt : section [{name}] non traduite",
            f"conanfile.txt: section [{name}] not translated",
        ) for name in sections if name not in ("requires", "options")]
        options = sections.get("options", [])
        used: set[str] = set()
        for line in sections.get("requires", []):
            if "[" in line:
                notes.append(t(f"conanfile.txt : {line}, intervalle de versions non traduit", f"conanfile.txt: {line}, version range not translated"))
                continue
            reference = line.split("#")[0]
            mine = [option for option in options if fnmatch.fnmatchcase(reference, option.partition(":")[0])]
            used.update(mine)
            source = config.DependencySource(type="conan", ref=line)
            requirements.append(config.Requirement(source=source, minimum=None, flags=[f"-o={option}" for option in mine]))
        notes += [t(
            f"conanfile.txt : option {option} non traduite, elle ne désigne aucune dépendance",
            f"conanfile.txt: option {option} not translated, it names no dependency",
        ) for option in options if option not in used]
    return config.Detection(targets=[], notes=notes, imported_from=None, requirements=requirements, files=files)


def _sections(text: str) -> dict[str, list[str]]:
    """Les lignes de chaque [section], sans les commentaires ni les lignes vides."""
    sections: dict[str, list[str]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1].strip(), [])
        elif current is not None:
            current.append(line)
    return sections
