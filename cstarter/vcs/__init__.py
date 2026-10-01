"""L'enveloppe de git.exe et le pilote de fusion des JSON de .cstarter/.

CStarter appelle git.exe, ne réimplémente rien de lui et n'écrit jamais lui-même dans .git/.

Ne dépend que de config/.
"""

from cstarter.vcs.git import (
    add,
    branches,
    clone,
    commit,
    create_branch,
    diff,
    github_accounts,
    github_login,
    in_head,
    init,
    lfs_available,
    log,
    remote_urls,
    remotes,
    restore,
    run,
    set_config,
    set_remote,
    status,
    toplevel,
)
from cstarter.vcs.merge import merge
