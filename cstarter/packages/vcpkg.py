"""La source et le builder vcpkg : un port de vcpkg, que vcpkg construit.

Le vcpkg livré avec Visual Studio ne connaît que le mode manifeste. La source écrit donc un
vcpkg.json dans le dossier de travail : le port, sa version exacte (le tag de la source) dans
overrides, et une builtin-baseline qui fige le registre, la plus récente si la source n'en a
pas. Le builder lance vcpkg install pour chaque plateforme, avec le triplet que désignent la
plateforme, le runtime et la liaison, puis recopie le résultat dans l'entrée, depuis debug/
pour une entrée de débogage. L'entrée contient aussi les ports dont celui-ci dépend.

Une option : linkage=dynamic, le défaut en MD, ou linkage=static. En MT, tout est statique.
"""

import json
import os
import re
from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import archive, layout
from cstarter.toolchain.vcpkg import run_vcpkg

_PORT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_REGISTRY = "https://api.github.com/repos/microsoft/vcpkg/commits/master"
_BASELINE = "https://raw.githubusercontent.com/microsoft/vcpkg/{}/versions/baseline.json"
_TRIPLETS = {"x64": "x64-windows", "x86": "x86-windows", "ARM64": "arm64-windows"}
_TOOLSET = "v143"


def fetch(source: config.DependencySource, work: Path) -> tuple[Path, config.DependencySource]:
    """Écrit dans work le manifeste du port. Renvoie son dossier et la source complétée de sa baseline."""
    if not _PORT.fullmatch(source.port or ""):
        raise PackageError(t(f"port vcpkg invalide : « {source.port} »", f"invalid vcpkg port: “{source.port}”"))
    if not source.tag:
        raise PackageError(
            t("source vcpkg : la version exacte du port est obligatoire (--tag)", "vcpkg source: the exact port version is required (--tag)")
        )
    baseline = source.baseline or _latest()
    if not _COMMIT.fullmatch(baseline):
        raise PackageError(t(f"baseline vcpkg invalide : « {baseline} »", f"invalid vcpkg baseline: “{baseline}”"))
    folder = work / "source"
    folder.mkdir()
    manifest = {
        "dependencies": [source.port],
        "overrides": [{"name": source.port, "version": source.tag}],
        "builtin-baseline": baseline,
    }
    (folder / "vcpkg.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return folder, config.DependencySource(type="vcpkg", tag=source.tag, port=source.port, baseline=baseline)


def build(source: Path, work: Path, stage: Path, flags: list[str], platforms: list[str], runtime: str | None) -> str:
    """Remplit stage pour chaque plateforme et renvoie le toolset de Visual Studio, celui de vcpkg."""
    static = (runtime or "").startswith("MT")
    for flag in flags:
        if flag not in ("linkage=static", "linkage=dynamic") or (static and flag == "linkage=dynamic"):
            raise PackageError(
                t(
                    f"builder vcpkg : option refusée « {flag} », linkage=static ou linkage=dynamic attendu, et MT est statique",
                    f"vcpkg builder: option “{flag}” refused, linkage=static or linkage=dynamic expected, and MT is static",
                )
            )
    suffix = "-static" if static else "-static-md" if "linkage=static" in flags else ""
    for platform in platforms:
        triplet = _TRIPLETS[platform] + suffix
        installed = work / f"installed-{platform}"
        run_vcpkg(
            [
                "install",
                f"--triplet={triplet}",
                f"--x-manifest-root={source}",
                f"--x-install-root={installed}",
                f"--x-buildtrees-root={work / 'buildtrees'}",
                f"--x-packages-root={work / 'packages'}",
            ]
        )
        tree = installed / triplet
        variant = tree / "debug" if (runtime or "").endswith("d") else tree
        if (tree / "include").is_dir():
            layout.copy_headers(tree / "include", stage)
        layout.copy_binaries(variant / "lib", stage / "lib" / platform, ".lib")
        layout.copy_binaries(variant / "bin", stage / "bin" / platform, ".dll")
    return _TOOLSET


def at_baseline(port: str, baseline: str | None) -> tuple[str, str]:
    """La baseline, la plus récente du registre si baseline vaut None, et la version du port
    qu'elle fixe : celle que vcpkg prend quand rien d'autre ne la fixe."""
    baseline = baseline or _latest()
    if not _COMMIT.fullmatch(baseline):
        raise PackageError(t(f"baseline vcpkg invalide : « {baseline} »", f"invalid vcpkg baseline: “{baseline}”"))
    data = json.loads(archive.read_text(_BASELINE.format(baseline)))
    entry = data.get("default", {}).get(port) if isinstance(data, dict) else None
    if not isinstance(entry, dict) or not isinstance(entry.get("baseline"), str):
        raise PackageError(t(f"le port vcpkg {port} n'est pas dans la baseline {baseline}", f"vcpkg port {port} is not in baseline {baseline}"))
    return baseline, entry["baseline"]


def _latest() -> str:
    """Le dernier commit du registre de vcpkg."""
    return archive.read_text(_REGISTRY, os.environ.get("GITHUB_TOKEN"), "application/vnd.github.sha").strip()
