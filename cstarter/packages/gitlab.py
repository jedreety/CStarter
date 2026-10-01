"""La source gitlab : un dépôt de gitlab.com, à un tag ou à un commit.

Comme pour github : le tag est résolu en commit, et c'est l'archive de ce commit qui est
téléchargée ; une branche se désigne par le commit où elle en est. Un jeton GITLAB_TOKEN, s'il
existe, sert aux dépôts privés. Il n'est écrit nulle part.
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from cstarter import config
from cstarter.errors import PackageError
from cstarter.language import t
from cstarter.packages import archive

# Un projet peut être rangé dans des sous-groupes : GROUPE/SOUS-GROUPE/PROJET.
REPOSITORY = re.compile(r"https://gitlab\.com/((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+?)(?:\.git)?/?", re.IGNORECASE)
_API = "https://gitlab.com/api/v4/projects"


def fetch(source: config.DependencySource, work: Path) -> tuple[Path, config.DependencySource]:
    """Télécharge et extrait dans work le commit de source, ou celui de son tag. Renvoie le
    dossier des sources et la source complétée : commit, empreintes de l'archive et du contenu."""
    match = REPOSITORY.fullmatch(source.url or "")
    if match is None:
        raise PackageError(
            t(
                f"dépôt GitLab attendu, https://gitlab.com/GROUPE/PROJET, pas « {source.url} »",
                f"GitLab repository expected, https://gitlab.com/GROUP/PROJECT, not “{source.url}”",
            )
        )
    path = match[1]
    project = f"{_API}/{quote(path, safe='')}"
    token = os.environ.get("GITLAB_TOKEN")
    commit = source.commit or _commit(project, path, source.tag, token)
    url = f"{project}/repository/archive.tar.gz?sha={commit}"
    folder, sha256, tree = archive.fetch(url, work, f"{path}@{commit}", source.sha256, source.tree_sha256, token)
    return folder, config.DependencySource(
        type="gitlab", url=f"https://gitlab.com/{path}", tag=source.tag, commit=commit, sha256=sha256, tree_sha256=tree
    )


def _commit(project: str, path: str, tag: str | None, token: str | None) -> str:
    """Le commit exact du tag, celui qu'il désigne même s'il est annoté."""
    if not tag:
        raise PackageError(t("source gitlab : le tag est obligatoire (--tag)", "gitlab source: the tag is required (--tag)"))
    data = json.loads(archive.read_text(f"{project}/repository/tags/{quote(tag, safe='')}", token))
    target = data.get("commit") if isinstance(data, dict) else None
    commit = target.get("id") if isinstance(target, dict) else None
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PackageError(t(f"{path}, tag {tag} : GitLab n'a pas renvoyé de commit", f"{path}, tag {tag}: GitLab returned no commit"))
    return commit


def versions(url: str) -> tuple[list[str], list[config.Branch]]:
    """Les tags du projet, et ses branches, la principale d'abord : les cent premiers de chaque."""
    match = REPOSITORY.fullmatch(url)
    if match is None:
        raise PackageError(
            t(
                f"dépôt GitLab attendu, https://gitlab.com/GROUPE/PROJET, pas « {url} »",
                f"GitLab repository expected, https://gitlab.com/GROUP/PROJECT, not “{url}”",
            )
        )
    path = match[1]
    project = f"{_API}/{quote(path, safe='')}"
    token = os.environ.get("GITLAB_TOKEN")
    try:
        tags = [tag["name"] for tag in json.loads(archive.read_text(f"{project}/repository/tags?per_page=100", token))]
        found = json.loads(archive.read_text(f"{project}/repository/branches?per_page=100", token))
        branches = [config.Branch(name=branch["name"], commit=branch["commit"]["id"]) for branch in found]
        default = {branch["name"] for branch in found if branch.get("default")}
    except (ValueError, KeyError, TypeError):
        raise PackageError(t(f"{path} : GitLab a renvoyé une liste illisible", f"{path}: GitLab returned an unreadable list")) from None
    return tags, sorted(branches, key=lambda branch: branch.name not in default)
