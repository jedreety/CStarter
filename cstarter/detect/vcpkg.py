"""Le détecteur vcpkg.json : les dépendances d'un manifeste de vcpkg.

Chaque dépendance devient une dépendance à installer par la source vcpkg, avec la
builtin-baseline du manifeste, et sa version si overrides la fixe, sinon son version>=.
Les features, les restrictions de plateforme, les dépendances d'outils et les registres
de vcpkg-configuration.json ne se traduisent pas : ils sont signalés.
"""

import json
from pathlib import Path

from cstarter import config
from cstarter.language import t

_KNOWN = {
    "$schema", "name", "version", "version-string", "version-semver", "version-date", "port-version",
    "description", "homepage", "license", "maintainers", "documentation", "supports",
    "dependencies", "overrides", "builtin-baseline",
}


def detect(folder: Path, execute: bool = False) -> config.Detection | None:
    """Les dépendances du vcpkg.json de folder, ou None s'il n'en a pas."""
    path = folder / "vcpkg.json"
    if not path.is_file():
        return None
    files = ["vcpkg.json"]
    notes = []
    if (folder / "vcpkg-configuration.json").is_file():
        files.append("vcpkg-configuration.json")
        notes.append(
            t(
                "vcpkg-configuration.json : registres non traduits, seul celui de Microsoft sert",
                "vcpkg-configuration.json: registries not translated, only Microsoft's is used",
            )
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return config.Detection(targets=[], notes=[t(
            f"vcpkg.json illisible : {error}",
            f"unreadable vcpkg.json: {error}",
        )], imported_from=None, files=files)
    if not isinstance(data, dict):
        return config.Detection(targets=[], notes=[t(
            "vcpkg.json : objet JSON attendu",
            "vcpkg.json: JSON object expected",
        )], imported_from=None, files=files)
    notes += [t(f"vcpkg.json : champ {key} non traduit", f"vcpkg.json: field {key} not translated") for key in data if key not in _KNOWN]
    baseline = data.get("builtin-baseline") if isinstance(data.get("builtin-baseline"), str) else None
    versions = {}
    for override in data.get("overrides", []):
        if isinstance(override, dict) and isinstance(override.get("name"), str):
            versions[override["name"]] = next(
                (override[key] for key in ("version", "version-semver", "version-date", "version-string") if key in override), None
            )
    requirements = []
    for dependency in data.get("dependencies", []):
        spec = {"name": dependency} if isinstance(dependency, str) else dependency
        if not isinstance(spec, dict) or not isinstance(spec.get("name"), str):
            notes.append(t(f"vcpkg.json : dépendance illisible {dependency}", f"vcpkg.json: unreadable dependency {dependency}"))
            continue
        name = spec["name"]
        if spec.get("host"):
            notes.append(
                t(f"vcpkg.json, {name} : dépendance d'outil (host) non traduite", f"vcpkg.json, {name}: tool (host) dependency not translated")
            )
            continue
        for key in ("features", "platform"):
            if spec.get(key):
                notes.append(t(f"vcpkg.json, {name} : {key} {spec[key]} non traduit", f"vcpkg.json, {name}: {key} {spec[key]} not translated"))
        if spec.get("default-features") is False:
            notes.append(t(f"vcpkg.json, {name} : default-features false non traduit", f"vcpkg.json, {name}: default-features false not translated"))
        source = config.DependencySource(type="vcpkg", port=name, tag=versions.get(name), baseline=baseline)
        requirements.append(config.Requirement(source=source, minimum=spec.get("version>="), flags=[]))
    return config.Detection(targets=[], notes=notes, imported_from=None, requirements=requirements, files=files)
