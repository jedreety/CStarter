"""Le modèle : les dataclasses du projet, de la solution et des targets, leur
lecture, leur validation et leur sérialisation stable. N'écrit rien.

Ne dépend de rien d'autre dans cstarter, sauf errors.py.
"""

from cstarter.config.dump import dump, dump_dependency, dump_lock, encode_json, lock_entry
from cstarter.config.load import load, load_dependency, load_lock, load_lock_entry
from cstarter.config.mapping import build_matrix, solution_configurations
from cstarter.config.merge import merge
from cstarter.config.model import (
    MSVC_PLATFORMS,
    MSVC_RUNTIMES,
    NAME,
    PLATFORMS,
    RUNTIMES,
    TARGET_TYPES,
    AnalysisReport,
    Branch,
    CMakeOption,
    Commit,
    Configuration,
    Debugger,
    Define,
    Dependency,
    DependencyBuild,
    DependencyRef,
    DependencySource,
    Detection,
    GitChange,
    GitReport,
    GitStatus,
    Link,
    Output,
    Pch,
    Prerequisite,
    Program,
    Project,
    Remote,
    Requirement,
    RestoreReport,
    Solution,
    SolutionTarget,
    Sources,
    Target,
    Update,
    Versions,
    default_configurations,
    new_target,
    safe_name,
)
from cstarter.config.sources import COMPILED, DEFINITIONS, HEADERS, RESOURCES, resolve_sources, walk
from cstarter.config.validate import check_dependencies, doubles_field, unmet_requirements, validate, validate_dependency
