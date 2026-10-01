"""La source et le builder conan : un package de conan 2, que conan construit.

La source résout la référence NOM/VERSION en sa révision exacte, sur les remotes de conan, et
l'écrit dans un conanfile.txt du dossier de travail. Le builder lance conan install pour chaque
plateforme, avec les réglages build_type, arch, compiler.runtime et compiler.runtime_type de
l'entrée, puis recopie dans l'entrée le package et ceux dont il dépend : headers, .lib et .dll.
Il crée le profil par défaut de conan s'il manque (conan profile detect). Un package sans binaire
pour ces réglages se construit depuis ses sources, avec le CMake que CStarter trouve, celui de
Visual Studio compris.

Options : celles qui fixent les options des packages, -o=MOTIF:OPTION=VALEUR, par exemple
-o=fmt/*:shared=True. Les réglages ne viennent que de l'entrée.
"""

import json
import re
import shutil
from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError, ToolchainError
from cstarter.language import t
from cstarter.packages import layout
from cstarter.toolchain.cmake import find_cmake
from cstarter.toolchain.conan import run_conan

_REFERENCE = re.compile(r"[a-z0-9_][a-z0-9_+.-]*/[A-Za-z0-9_+.-]+(?:@[a-z0-9_+.-]+/[a-z0-9_+.-]+)?")
_REVISION = re.compile(r"[0-9a-f]{32}")
_ACCEPTED = re.compile(r"-o(?::h)?=\S+:\S+=\S*")
_ARCHITECTURES = {"x64": "x86_64", "x86": "x86", "ARM64": "armv8"}
_TOOLSET = "v143"


def fetch(source: config.DependencySource, work: Path) -> tuple[Path, config.DependencySource]:
    """Écrit dans work le conanfile.txt de la référence, à sa révision exacte. Renvoie son dossier
    et la source complétée de la révision."""
    if source.tag is not None:
        raise PackageError(t("source conan : pas de tag, la référence porte la version", "conan source: no tag, the reference carries the version"))
    reference, _, revision = (source.ref or "").partition("#")
    if not _REFERENCE.fullmatch(reference):
        raise PackageError(
            t(f"référence conan attendue, NOM/VERSION, pas « {source.ref} »", f"conan reference expected, NAME/VERSION, not “{source.ref}”")
        )
    revision = revision or _latest(reference)
    if not _REVISION.fullmatch(revision):
        raise PackageError(t(f"{reference} : révision conan invalide « {revision} »", f"{reference}: invalid conan revision “{revision}”"))
    folder = work / "source"
    folder.mkdir()
    (folder / "conanfile.txt").write_text(f"[requires]\n{reference}#{revision}\n", encoding="utf-8")
    return folder, config.DependencySource(type="conan", ref=f"{reference}#{revision}")


def build(source: Path, work: Path, stage: Path, flags: list[str], platforms: list[str], runtime: str | None) -> str:
    """Remplit stage pour chaque plateforme et renvoie le toolset de Visual Studio, celui du profil."""
    for flag in flags:
        if not _ACCEPTED.fullmatch(flag):
            raise PackageError(
                t(
                    f"builder conan : option refusée « {flag} », -o=MOTIF:OPTION=VALEUR attendu",
                    f"conan builder: option “{flag}” refused, -o=PATTERN:OPTION=VALUE expected",
                )
            )
    build_type = "Debug" if (runtime or "").endswith("d") else "Release"
    try:
        tools = [find_cmake().parent]
    except ToolchainError:
        tools = []  # conan cherchera cmake dans le PATH
    run_conan(["profile", "detect", "--exist-ok"])
    for platform in platforms:
        deployed = work / f"deploy-{platform}"
        run_conan(
            [
                "install",
                str(source),
                f"--output-folder={work / f'conan-{platform}'}",
                "--build=missing",
                "-s",
                f"build_type={build_type}",
                "-s",
                f"arch={_ARCHITECTURES[platform]}",
                "-s",
                f"compiler.runtime={'static' if (runtime or '').startswith('MT') else 'dynamic'}",
                "-s",
                f"compiler.runtime_type={build_type}",
                "--deployer=full_deploy",
                f"--deployer-folder={deployed}",
                *flags,
            ],
            path=tools,
        )
        # full_deploy copie chaque package, et son conanmanifest.txt, sous full_deploy/host/.
        headers = work / f"include-{platform}"
        for manifest in sorted(deployed.glob("full_deploy/host/**/conanmanifest.txt")):
            package = manifest.parent
            if (package / "include").is_dir():
                shutil.copytree(package / "include", headers, dirs_exist_ok=True, copy_function=shutil.copyfile)
            layout.copy_binaries(package / "lib", stage / "lib" / platform, ".lib")
            layout.copy_binaries(package / "bin", stage / "bin" / platform, ".dll")
        if headers.is_dir():
            layout.copy_headers(headers, stage)
    return _TOOLSET


def _latest(reference: str) -> str:
    """La dernière révision de la recette, sur le premier remote qui la connaît."""
    listed = json.loads(run_conan(["list", f"{reference}#latest", "--remote=*", "--format=json"], capture=True))
    for remote in listed.values():
        found = remote.get(reference) if isinstance(remote, dict) else None
        revisions = found.get("revisions") if isinstance(found, dict) else None
        if isinstance(revisions, dict) and revisions:
            return next(iter(revisions))
    raise PackageError(t(f"{reference} : aucun remote de conan ne connaît cette référence", f"{reference}: no conan remote knows this reference"))
