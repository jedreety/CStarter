"""Le détecteur git : les remotes, les branches et l'historique récent.

Ils sont montrés à l'utilisateur, jamais recopiés dans .cstarter/ : git reste leur source.
Le détecteur lit par git.exe et n'écrit jamais dans .git/.
"""

from pathlib import Path

from cstarter import config
from cstarter.errors import ToolchainError
from cstarter.language import t
from cstarter.toolchain.git import git_output


def detect(folder: Path, execute: bool = False) -> config.Detection | None:
    """Ce que le dépôt git de folder montre, ou None si folder n'en est pas un."""
    if not (folder / ".git").exists():
        return None
    try:
        remotes = sorted(set(git_output(folder, ["remote", "-v"]).split("\n")) - {""})
        branches = git_output(folder, ["branch", "--format=%(refname:short)"]).split()
        current = git_output(folder, ["branch", "--show-current"]).strip()
    except ToolchainError as error:
        return config.Detection(targets=[], notes=[t(f"git : {error}", f"git: {error}")], imported_from=None)
    try:
        history = git_output(folder, ["log", "--oneline", "-5"]).splitlines()
    except ToolchainError:
        history = []  # un dépôt sans commit
    info = [f"remote {' '.join(remote.split())}" for remote in remotes]
    info.append(
        t(f"branches : {', '.join(branches) or 'aucune'}", f"branches: {', '.join(branches) or 'none'}")
        + (t(f", courante {current}", f", current {current}") if current else "")
    )
    info += [f"commit {line}" for line in history] or [t("aucun commit", "no commit")]
    return config.Detection(targets=[], notes=[], imported_from=None, info=info)
