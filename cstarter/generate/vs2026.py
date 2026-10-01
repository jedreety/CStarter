"""Le générateur Visual Studio 2026 : celui de Visual Studio 2022, avec
l'en-tête de solution et le VCProjectVersion de la version 18, et le toolset v145.
"""

from cstarter import config
from cstarter.generate import vs2022

# Visual Studio 2026, version 18.0.
_VS2026 = vs2022.Version(major=18, build="18.0.11205.157", toolset="v145")
TOOLSET = _VS2026.toolset
SUFFIXES = vs2022.SUFFIXES


def generate(project: config.Project, dependencies: dict[tuple[str, str], config.Dependency]) -> dict[str, bytes]:
    """Les fichiers de la solution, comme vs2022.generate."""
    return vs2022.generate(project, dependencies, _VS2026)
