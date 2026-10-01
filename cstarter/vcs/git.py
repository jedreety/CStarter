"""git.exe, celui du PATH. Les commandes que l'utilisateur suit (clone, pull,
push, merge) écrivent au terminal ; celles dont CStarter lit la réponse sont capturées. Les chemins
d'un dépôt sont relatifs à sa racine, comme git status les donne.
"""

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from cstarter import config
from cstarter.errors import ToolchainError
from cstarter.language import t


def run(folder: Path, arguments: Sequence[str]) -> int:
    """Lance git dans folder, sa sortie au terminal, et renvoie son code de sortie."""
    return subprocess.run([_git(), "-C", str(folder), *arguments], check=False).returncode


def toplevel(folder: Path) -> Path | None:
    """La racine du dépôt qui contient folder, ou None s'il n'est dans aucun."""
    result = _capture(folder, ["rev-parse", "--show-toplevel"])
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def init(folder: Path) -> None:
    _check(run(folder, ["init"]), "init")


def clone(url: str, destination: Path) -> None:
    """Clone url dans destination ; -- empêche une URL de passer pour une option."""
    _check(subprocess.run([_git(), "clone", "--", url, str(destination)], check=False).returncode, "clone")


def status(root: Path) -> config.GitStatus:
    """L'état du dépôt dont root est la racine, d'après git status --porcelain=v2."""
    fields = iter(_output(root, ["status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all"]).split("\0"))
    merging = _capture(root, ["rev-parse", "-q", "--verify", "MERGE_HEAD"]).returncode == 0
    state = config.GitStatus(root=root, branch=None, upstream=None, ahead=0, behind=0, merging=merging, changes=[])
    for field in fields:
        kind, _, rest = field.partition(" ")
        if field.startswith("# branch.head "):
            head = field.removeprefix("# branch.head ")
            state.branch = None if head == "(detached)" else head
        elif field.startswith("# branch.upstream "):
            state.upstream = field.removeprefix("# branch.upstream ")
        elif field.startswith("# branch.ab "):
            ahead, behind = field.removeprefix("# branch.ab ").split()
            state.ahead, state.behind = int(ahead), -int(behind)
        elif kind in ("1", "u"):
            # 1 XY sub mH mI mW hH hI chemin ; u XY sub m1 m2 m3 mW h1 h2 h3 chemin
            parts = rest.split(" ", 7 if kind == "1" else 9)
            state.changes.append(config.GitChange(parts[-1], parts[0][0], parts[0][1], kind == "u"))
        elif kind == "2":
            # 2 XY sub mH mI mW hH hI Xscore chemin, puis l'ancien chemin dans le champ suivant
            parts = rest.split(" ", 8)
            state.changes.append(config.GitChange(parts[-1], parts[0][0], parts[0][1], False, next(fields)))
        elif kind == "?":
            state.changes.append(config.GitChange(rest, "?", "?", False))
    return state


def add(root: Path, paths: Sequence[str]) -> None:
    _check(run(root, ["add", "--", *paths]), "add")


def commit(root: Path, message: str, paths: Sequence[str] = ()) -> None:
    """Valide ce qui est préparé, ou seulement paths s'il y en a."""
    _check(run(root, ["commit", "-m", message, *(["--", *paths] if paths else [])]), "commit")


def branches(root: Path) -> list[str]:
    """Les branches locales, triées."""
    return sorted(_output(root, ["branch", "--format=%(refname:short)"]).split())


def create_branch(root: Path, name: str) -> None:
    _check(run(root, ["branch", name]), "branch")


def remotes(root: Path) -> list[str]:
    return _output(root, ["remote"]).split()


def remote_urls(root: Path) -> list[config.Remote]:
    """Les remotes du dépôt et leur adresse de récupération, triés par nom."""
    found = {}
    for line in _output(root, ["remote", "-v"]).splitlines():
        name, _, rest = line.partition("\t")
        url, _, kind = rest.rpartition(" ")
        if kind == "(fetch)":
            found[name] = url
    return [config.Remote(name=name, url=url) for name, url in sorted(found.items())]


def set_remote(root: Path, name: str, url: str) -> None:
    """Ajoute le remote name, ou change son adresse s'il existe."""
    _check(run(root, ["remote", "set-url" if name in remotes(root) else "add", name, url]), "remote")


def has_head(root: Path) -> bool:
    """Le dépôt a-t-il un premier commit ?"""
    return _capture(root, ["rev-parse", "-q", "--verify", "HEAD"]).returncode == 0


def in_head(root: Path, path: str) -> bool:
    """path, relatif à la racine, existe-t-il dans le dernier commit ?"""
    return _capture(root, ["cat-file", "-e", f"HEAD:{path}"]).returncode == 0


def log(root: Path, count: int) -> list[config.Commit]:
    """Les count derniers commits de la branche courante, le plus récent d'abord."""
    if not has_head(root):
        return []
    text = _output(root, ["log", f"-n{count}", "--format=%H%x1f%s%x1f%an%x1f%aI%x1e"])
    commits = []
    for record in text.split("\x1e"):
        fields = record.strip("\n").split("\x1f")
        if len(fields) == 4:
            commits.append(config.Commit(hash=fields[0], subject=fields[1], author=fields[2], date=fields[3]))
    return commits


def diff(root: Path, path: str, original: str | None, untracked: bool) -> str:
    """Les modifications de path depuis le dernier commit, index et dossier de travail ensemble, au
    format unifié de git. Un fichier non suivi, ou un dépôt sans commit, les montre en entier."""
    if untracked or not has_head(root):
        result = _capture(root, ["diff", "--no-color", "--no-index", "--", "/dev/null", path])
        if result.returncode not in (0, 1):  # 1 : les fichiers diffèrent
            raise ToolchainError(t(f"git diff : {result.stderr.strip()}", f"git diff: {result.stderr.strip()}"))
        return result.stdout
    return _output(root, ["diff", "--no-color", "-M", "HEAD", "--", path, *([original] if original else [])])


def restore(root: Path, paths: Sequence[str]) -> None:
    """Rend à paths leur contenu du dernier commit, dans l'index et dans le dossier de travail."""
    _check(run(root, ["restore", "--source=HEAD", "--staged", "--worktree", "--", *paths]), "restore")


def set_config(root: Path, key: str, value: str) -> None:
    """Écrit key dans la configuration locale du dépôt, .git/config, par git config."""
    _check(run(root, ["config", "--local", key, value]), "config")


def lfs_available(root: Path) -> bool:
    """Git LFS est-il installé avec git ?"""
    return _capture(root, ["lfs", "version"]).returncode == 0


def github_accounts() -> list[str]:
    """Les comptes GitHub que Git Credential Manager connaît : leurs noms seuls, jamais leurs jetons.
    Aucun sans Git Credential Manager."""
    result = subprocess.run(
        [_git(), "credential-manager", "github", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    return result.stdout.split() if result.returncode == 0 else []


def github_login() -> None:
    """Connecte un compte GitHub par Git Credential Manager, qui ouvre sa propre fenêtre : le jeton va
    de GitHub à lui sans passer par CStarter. Refermer cette fenêtre n'est pas une erreur, le compte
    reste inconnu ; seule l'absence de Git Credential Manager en est une."""
    if subprocess.run([_git(), "credential-manager", "--version"], capture_output=True, check=False).returncode != 0:
        raise ToolchainError(
            t(
                "Git Credential Manager introuvable : il s'installe avec Git (winget install --id Git.Git --exact)",
                "Git Credential Manager not found: it comes with Git (winget install --id Git.Git --exact)",
            )
        )
    subprocess.run([_git(), "credential-manager", "github", "login"], check=False)


def _output(folder: Path, arguments: Sequence[str]) -> str:
    """La sortie de git lancé dans folder. Un échec lève ToolchainError, avec le message de git."""
    result = _capture(folder, arguments)
    if result.returncode != 0:
        raise ToolchainError(
            t(
                f"git {arguments[0]} : {result.stderr.strip() or result.stdout.strip()}",
                f"git {arguments[0]}: {result.stderr.strip() or result.stdout.strip()}",
            )
        )
    return result.stdout


def _capture(folder: Path, arguments: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_git(), "-C", str(folder), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _check(code: int, command: str) -> None:
    if code != 0:
        raise ToolchainError(
            t(f"git {command} a échoué, code {code} : son message est plus haut", f"git {command} failed, code {code}: its message is above")
        )


def _git() -> str:
    found = shutil.which("git")
    if found is None:
        raise ToolchainError(
            t(
                "git introuvable : installez Git (winget install --id Git.Git --exact)",
                "git not found: install Git (winget install --id Git.Git --exact)",
            )
        )
    return found
