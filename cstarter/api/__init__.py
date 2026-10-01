"""Les fonctions publiques : projet, solution, targets, dépendances, git, distribution et
prérequis.

Seule couche d'orchestration : cli.py et gui/ n'appellent qu'elle, et seule elle
appelle write.py.
"""

from cstarter.api.dependencies import (
    analyze_dependency,
    get_dependencies,
    get_dependency,
    install_dependency,
    install_for_project,
    link_dependency,
    list_all_dependencies,
    list_versions,
    remove_dependency,
    unlink_dependency,
)
from cstarter.api.distribution import VERSION, check_update, download_update, executable, install_update, update_disabled
from cstarter.api.git import (
    add,
    branch,
    clone,
    commit,
    diff,
    discard,
    github_account,
    github_login,
    init,
    log,
    merge,
    merge_driver,
    pull,
    push,
    remote,
    status,
    switch,
)
from cstarter.api.portability import export_as_dependency, restore, unvendor_dependency, vendor_dependency
from cstarter.api.prerequisites import install_prerequisite, prerequisites
from cstarter.api.project import (
    build,
    build_all,
    check_program,
    clean,
    create_from_template,
    create_project,
    create_starter,
    detect,
    detect_sources,
    find_project,
    generate,
    get_program,
    get_project,
    remove_old_files,
    run,
    save_project,
)
from cstarter.api.solution import (
    add_global_define,
    add_platform,
    add_project_reference,
    remove_global_define,
    remove_platform,
    remove_project_reference,
    set_project_reference,
    set_sln_output,
    set_startup_target,
)
from cstarter.api.targets import (
    add_config_define,
    add_configuration,
    add_include_dir,
    add_vcxproj,
    create_vcxproj,
    get_vcxproj,
    get_vcxprojs,
    remove_config_define,
    remove_configuration,
    remove_vcxproj,
    rename_configuration,
    rename_vcxproj,
    set_pch,
    set_public_headers,
    set_source_dirs,
    set_vcxproj_dir,
)
from cstarter.config import TARGET_TYPES
from cstarter.packages import BUILDERS
