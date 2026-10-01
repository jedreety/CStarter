"""Le builder cmake.

Pour chaque plateforme : configuration avec le générateur Visual Studio 2022 et -A, le
runtime imposé par CMAKE_MSVC_RUNTIME_LIBRARY, construction de la configuration que le
runtime désigne (Debug pour MDd et MTd, Release sinon), puis cmake --install dans le
dossier de travail. Les headers, les .lib, les .dll et leurs .pdb installés forment
l'entrée ; le reste de l'installation (lib/cmake, share…) est ignoré.
"""

import re
from pathlib import Path

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import layout
from cstarter.toolchain.cmake import run_cmake

_GENERATOR = "Visual Studio 17 2022"
_TOOLSET = "v143"
_ARCHITECTURES = config.MSVC_PLATFORMS
_RUNTIMES = config.MSVC_RUNTIMES
# Une option doit être un -D qui ne touche ni au générateur ni au runtime notés dans metadata.json.
_ACCEPTED = re.compile(r"-D(?!\s*CMAKE_(MSVC_RUNTIME_LIBRARY|GENERATOR)).+", re.IGNORECASE)


def build(source: Path, work: Path, stage: Path, flags: list[str], platforms: list[str], runtime: str | None) -> str:
    """Remplit stage pour chaque plateforme et renvoie le toolset utilisé."""
    for flag in flags:
        if not _ACCEPTED.fullmatch(flag):
            raise PackageError(
                t(
                    f"builder cmake : option refusée « {flag} », seuls les -DVARIABLE=VALEUR sont acceptés, hors générateur et runtime",
                    f"cmake builder: option “{flag}” refused, only -DVARIABLE=VALUE is accepted, except generator and runtime",
                )
            )
    configuration = "Debug" if (runtime or "").endswith("d") else "Release"
    for platform in platforms:
        tree = work / f"build-{platform}"
        prefix = work / f"install-{platform}"
        run_cmake(
            [
                "-S",
                str(source),
                "-B",
                str(tree),
                "-G",
                _GENERATOR,
                "-A",
                _ARCHITECTURES[platform],
                f"-DCMAKE_MSVC_RUNTIME_LIBRARY={_RUNTIMES[runtime or '']}",
                "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
                *flags,
            ]
        )
        # Le dossier de travail est sous %TEMP% à dessein : MSBuild n'a pas à le signaler (MSB8029).
        run_cmake(["--build", str(tree), "--config", configuration, "--", "-p:IgnoreWarnIntDirInTempDetected=true"])
        run_cmake(["--install", str(tree), "--config", configuration, "--prefix", str(prefix)])
        if (prefix / "include").is_dir():
            layout.copy_headers(prefix / "include", stage)
        layout.copy_binaries(prefix / "lib", stage / "lib" / platform, ".lib")
        layout.copy_binaries(prefix / "bin", stage / "bin" / platform, ".dll")
    return _TOOLSET
