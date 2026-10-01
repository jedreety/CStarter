"""La source github : un dépôt GitHub, à un tag ou à un commit.

Le tag est résolu en commit, et c'est l'archive de ce commit qui est téléchargée : un
tag déplacé ne change pas ce que restore reconstruira. Une branche se désigne par le commit
où elle en est. Un jeton GITHUB_TOKEN, s'il existe, sert aux dépôts privés et à la limite de
débit de l'API. Il n'est écrit nulle part.
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

REPOSITORY = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", re.IGNORECASE)
_API = "https://api.github.com/repos"


def fetch(source: config.DependencySource, work: Path) -> tuple[Path, config.DependencySource]:
    """Télécharge et extrait dans work le commit de source, ou celui de son tag. Renvoie le
    dossier des sources et la source complétée : commit, empreintes de l'archive et du contenu."""
    match = REPOSITORY.fullmatch(source.url or "")
    if match is None:
        raise PackageError(
            t(
                f"dépôt GitHub attendu, https://github.com/PROPRIÉTAIRE/DÉPÔT, pas « {source.url} »",
                f"GitHub repository expected, https://github.com/OWNER/REPOSITORY, not “{source.url}”",
            )
        )
    owner, repository = match.groups()
    token = os.environ.get("GITHUB_TOKEN")
    commit = source.commit or _commit(owner, repository, source.tag, token)
    url = f"{_API}/{owner}/{repository}/tarball/{commit}"
    folder, sha256, tree = archive.fetch(url, work, f"{owner}/{repository}@{commit}", source.sha256, source.tree_sha256, token)
    return folder, config.DependencySource(
        type="github",
        url=f"https://github.com/{owner}/{repository}",
        tag=source.tag,
        commit=commit,
        sha256=sha256,
        tree_sha256=tree,
    )


def _commit(owner: str, repository: str, tag: str | None, token: str | None) -> str:
    """Le commit exact du tag. Une branche du même nom n'est pas un tag : GitHub la refuse."""
    if not tag:
        raise PackageError(t("source github : le tag est obligatoire (--tag)", "github source: the tag is required (--tag)"))
    commit = archive.read_text(
        f"{_API}/{owner}/{repository}/commits/refs/tags/{quote(tag, safe='')}", token, "application/vnd.github.sha"
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PackageError(
            t(f"{owner}/{repository}, tag {tag} : GitHub n'a pas renvoyé de commit", f"{owner}/{repository}, tag {tag}: GitHub returned no commit")
        )
    return commit


def versions(url: str) -> tuple[list[str], list[config.Branch]]:
    """Les tags du dépôt, et ses branches, la principale d'abord : les cent premiers de chaque."""
    match = REPOSITORY.fullmatch(url)
    if match is None:
        raise PackageError(
            t(
                f"dépôt GitHub attendu, https://github.com/PROPRIÉTAIRE/DÉPÔT, pas « {url} »",
                f"GitHub repository expected, https://github.com/OWNER/REPOSITORY, not “{url}”",
            )
        )
    owner, repository = match.groups()
    token = os.environ.get("GITHUB_TOKEN")
    base = f"{_API}/{owner}/{repository}"
    try:
        default = json.loads(archive.read_text(base, token))["default_branch"]
        tags = [tag["name"] for tag in json.loads(archive.read_text(f"{base}/tags?per_page=100", token))]
        branches = [
            config.Branch(name=branch["name"], commit=branch["commit"]["sha"])
            for branch in json.loads(archive.read_text(f"{base}/branches?per_page=100", token))
        ]
    except (ValueError, KeyError, TypeError):
        raise PackageError(
            t(f"{owner}/{repository} : GitHub a renvoyé une liste illisible", f"{owner}/{repository}: GitHub returned an unreadable list")
        ) from None
    return tags, sorted(branches, key=lambda branch: branch.name != default)
