"""L'intégration git : init, clone, status, add, commit, push, pull, branch,
switch, merge, remote, log, diff, discard, le pilote de fusion des JSON de .cstarter/ que git
lance, et le compte GitHub que Git Credential Manager connaît.

git passe par vcs/. La configuration locale du dépôt s'écrit par git config, jamais directement
dans .git/. Les fichiers générés ne sont pas versionnés : init les ignore, et après pull, merge et
switch, qui ont pu changer .cstarter/, la solution est régénérée.

Sauf celles du compte GitHub, ces fonctions reçoivent la racine du projet, que find_project trouve,
et non le projet chargé : pendant un conflit, .cstarter/ ne se lit pas, et git doit pourtant servir
à le résoudre.
"""

import sys
from collections.abc import Collection, Sequence
from pathlib import Path

import cstarter
from cstarter import config, vcs, write
from cstarter.api.distribution import executable
from cstarter.api.portability import restore
from cstarter.api.project import generate
from cstarter.errors import CStarterError, NotARepositoryError, ProjectNotFoundError, ToolchainError, UnmarkedFileError
from cstarter.generate import MARK
from cstarter.language import t

_MARK = MARK.encode("utf-8")
# Les fichiers que la génération reconstruit depuis .cstarter/ : ils ne sont pas versionnés.
_GENERATED = ["*.sln", "*.vcxproj", "*.vcxproj.filters", "*.vcxproj.user"]
_ATTRIBUTES = [
    "# JSON de .cstarter/, fusionnés par CStarter selon leur structure",
    ".cstarter/**/*.json text eol=lf merge=cstarter",
]
# Les binaires vendorés, dans Git LFS si l'utilisateur le choisit.
_LFS = [
    "# Binaires de .cstarter/vendor/, dans Git LFS",
    ".cstarter/vendor/**/lib/** filter=lfs diff=lfs merge=lfs -text",
    ".cstarter/vendor/**/bin/** filter=lfs diff=lfs merge=lfs -text",
]


def init(root: Path, lfs: bool = False, confirmed: Collection[str] = ()) -> list[str]:
    """Crée un dépôt git à la racine du projet s'il n'est dans aucun, puis le configure :
    .gitignore exclut les fichiers générés et les sorties de compilation, .gitattributes confie les
    JSON de .cstarter/ au pilote de fusion et, avec lfs, les binaires vendorés à Git LFS. Le
    pilote est déclaré dans la configuration locale du dépôt. Renvoie les fichiers écrits.

    Un .gitignore ou un .gitattributes existant ne reçoit que les lignes qui lui manquent, à la fin,
    et seulement s'il figure dans confirmed. Sinon UnmarkedFileError le nomme, et rien n'est fait."""
    project = config.load(root)
    if lfs and not vcs.lfs_available(root):
        raise ToolchainError(
            t(
                "Git LFS introuvable : il s'installe avec Git for Windows (winget install --id Git.Git --exact)",
                "Git LFS not found: it comes with Git for Windows (winget install --id Git.Git --exact)",
            )
        )
    files = {}
    for name, lines in ((".gitignore", _ignored(project)), (".gitattributes", _ATTRIBUTES + (_LFS if lfs else []))):
        content = _completed(root / name, lines)
        if content is not None:
            files[name] = content
    written = write.write_files(root, files, _MARK, confirmed)
    if vcs.toplevel(root) is None:
        vcs.init(root)
    _declare_driver(root)
    if lfs:
        vcs.run(root, ["lfs", "install", "--local"])
    return written


def clone(url: str, location: Path | None = None) -> tuple[config.Project, config.RestoreReport]:
    """Clone url dans location, par défaut un dossier au nom du dépôt sous le dossier courant, comme
    git, puis le configure : le pilote de fusion, et restore, qui reconstruit dans le cache les
    entrées liées qui y manquent. La génération suit par generate, quand restore n'a rien
    laissé à fournir : elle peut demander une confirmation."""
    destination = (location or Path.cwd() / _repository_name(url)).resolve()
    vcs.clone(url, destination)
    if not (destination / ".cstarter").is_dir():
        raise ProjectNotFoundError(
            t(
                f"dépôt cloné dans {destination}, mais sans projet CStarter à sa racine",
                f"repository cloned into {destination}, but without a CStarter project at its root",
            )
        )
    project = config.load(destination)
    _declare_driver(destination)
    return project, restore(project)


def status(root: Path) -> config.GitStatus:
    """L'état du dépôt du projet : sa branche, et les fichiers qui ont changé, leurs chemins relatifs
    à la racine du dépôt."""
    return vcs.status(_repository(root))


def add(root: Path, paths: Sequence[str]) -> None:
    """Prépare paths pour le prochain commit, comme git add : absolus, ou relatifs à la racine du
    dépôt."""
    if not paths:
        raise CStarterError(t("aucun fichier à préparer", "no file to stage"))
    vcs.add(_repository(root), paths)


def commit(root: Path, message: str, paths: Sequence[str] = ()) -> None:
    """Valide ce qui est préparé ou, avec paths, ces fichiers seulement (git commit -- paths)."""
    if not message.strip():
        raise CStarterError(t("le message du commit est vide", "the commit message is empty"))
    vcs.commit(_repository(root), message, paths)


def push(root: Path) -> None:
    """Envoie la branche courante. Si elle ne suit encore aucune branche distante, elle suit celle de
    même nom sur origin, ou sur le seul remote du dépôt."""
    repository = _repository(root)
    state = vcs.status(repository)
    if state.branch is None:
        raise CStarterError(
            t("HEAD est détachée : placez-vous d'abord sur une branche (switch)", "HEAD is detached: switch to a branch first (switch)")
        )
    arguments = ["push"]
    if state.upstream is None:
        remotes = vcs.remotes(repository)
        if not remotes:
            raise CStarterError(
                t("le dépôt n'a aucun remote : cstarter remote origin URL l'ajoute", "the repository has no remote: cstarter remote origin URL adds one")
            )
        arguments += ["--set-upstream", "origin" if "origin" in remotes else remotes[0], state.branch]
    if vcs.run(repository, arguments) != 0:
        raise ToolchainError(t("git push a échoué : son message est plus haut", "git push failed: its message is above"))


def pull(root: Path, confirmed: Collection[str] = ()) -> config.GitReport:
    """git pull, puis ce qu'il laisse : les conflits, sinon la solution régénérée."""
    repository = _repository(root)
    return _after(root, repository, vcs.run(repository, ["pull"]), "pull", confirmed)


def branch(root: Path, name: str | None = None) -> list[str]:
    """Crée la branche name, sans s'y placer : switch le fait. Renvoie les branches locales."""
    repository = _repository(root)
    if name is not None:
        vcs.create_branch(repository, _branch_name(name))
    return vcs.branches(repository)


def switch(root: Path, name: str, create: bool = False, confirmed: Collection[str] = ()) -> config.GitReport:
    """Se place sur la branche name, créée d'abord avec create, puis régénère la solution depuis son
    .cstarter/."""
    repository = _repository(root)
    code = vcs.run(repository, ["switch", *(["-c"] if create else []), _branch_name(name)])
    return _after(root, repository, code, "switch", confirmed)


def merge(root: Path, name: str, confirmed: Collection[str] = ()) -> config.GitReport:
    """Fusionne la branche name dans la branche courante : le pilote fusionne les JSON de
    .cstarter/ selon leur structure. Puis ce que la fusion laisse, comme pour pull."""
    repository = _repository(root)
    return _after(root, repository, vcs.run(repository, ["merge", _branch_name(name)]), "merge", confirmed)


def remote(root: Path, name: str | None = None, url: str | None = None) -> list[config.Remote]:
    """Les remotes du dépôt et leur adresse. Avec name et url, ajoute le remote name, ou change son
    adresse s'il existe : push peut alors envoyer."""
    repository = _repository(root)
    if name is not None or url is not None:
        if not name or not url or name.startswith("-") or url.startswith("-"):
            raise CStarterError(t("un remote demande un nom et une adresse : cstarter remote origin URL", "a remote needs a name and an address: cstarter remote origin URL"))
        vcs.set_remote(repository, name, url)
    return vcs.remote_urls(repository)


def log(root: Path, count: int = 50) -> list[config.Commit]:
    """Les derniers commits de la branche courante, le plus récent d'abord : vide sans commit."""
    return vcs.log(_repository(root), count)


def diff(root: Path, path: str) -> str:
    """Les modifications du fichier path, relatif à la racine du dépôt, depuis le dernier commit :
    celles de l'index et du dossier de travail ensemble, au format unifié de git. Un fichier non
    suivi paraît ajouté en entier."""
    repository = _repository(root)
    change = _change(repository, path)
    return vcs.diff(repository, path, change.original, change.index == "?")


def discard(root: Path, paths: Sequence[str], confirmed: Collection[str] = ()) -> config.GitReport:
    """Annule les modifications de paths, relatifs à la racine du dépôt : leur contenu du dernier
    commit revient, dans l'index et dans le dossier de travail. L'appelant a la confirmation de
    l'utilisateur. Seul un fichier que le dernier commit contient se rétablit : un fichier nouveau
    serait supprimé, et CStarter ne supprime pas un fichier de l'utilisateur. Puis,
    comme après pull, la solution régénérée depuis .cstarter/."""
    repository = _repository(root)
    if not paths:
        raise CStarterError(t("aucun fichier à rétablir", "no file to restore"))
    for path in paths:
        change = _change(repository, path)
        if change.conflicted:
            raise CStarterError(t(f"{path} est en conflit : résolvez-le d'abord", f"{path} is in conflict: resolve it first"))
        if change.original or not vcs.in_head(repository, path):
            raise CStarterError(
                t(
                    f"{path} n'est pas dans le dernier commit : l'annuler le supprimerait",
                    f"{path} is not in the last commit: discarding it would delete it",
                )
            )
    vcs.restore(repository, paths)
    return _after(root, repository, 0, "restore", confirmed)


def _change(repository: Path, path: str) -> config.GitChange:
    """Ce que git status montre de path, qui doit avoir changé."""
    change = next((change for change in vcs.status(repository).changes if change.path == path), None)
    if change is None:
        raise CStarterError(t(f"{path} n'a pas changé depuis le dernier commit", f"{path} has not changed since the last commit"))
    return change


def merge_driver(
    base: Path, ours: Path, theirs: Path, marker_size: int = 7, labels: tuple[str, str] = ("ours", "theirs")
) -> list[str]:
    """Le pilote de fusion que git lance pour un JSON de .cstarter/ : fusionne base, ours et
    theirs, les fichiers temporaires de git, selon leur structure, écrit le résultat dans ours, et
    renvoie ce qui reste en conflit, vide si la fusion est propre."""
    merged, conflicts = vcs.merge(base.read_bytes(), ours.read_bytes(), theirs.read_bytes(), marker_size, labels)
    ours = ours.resolve()
    write.write_files(ours.parent, {ours.name: merged}, mark=None)
    return conflicts


def github_account() -> str | None:
    """Le compte GitHub que Git Credential Manager connaît, le premier s'il en connaît plusieurs,
    ou None : l'accueil de l'interface le montre. Seul son nom en sort, jamais son jeton."""
    accounts = vcs.github_accounts()
    return accounts[0] if accounts else None


def github_login() -> str | None:
    """Connecte un compte GitHub par Git Credential Manager, dans sa fenêtre à lui, puis le renvoie
    comme github_account : None si l'utilisateur a refermé la fenêtre sans se connecter."""
    vcs.github_login()
    return github_account()


def _after(root: Path, repository: Path, code: int, command: str, confirmed: Collection[str]) -> config.GitReport:
    """Ce que pull, merge ou switch laisse : les conflits, ceux de .cstarter/ d'abord ; sinon la
    solution régénérée depuis .cstarter/, ou ce qui l'en a empêché."""
    changes = vcs.status(repository).changes
    conflicts = sorted((change.path for change in changes if change.conflicted), key=_cstarter_first)
    if conflicts:
        return config.GitReport(conflicts=conflicts, problem=None, written=[])
    if code != 0:
        raise ToolchainError(t(f"git {command} a échoué : son message est plus haut", f"git {command} failed: its message is above"))
    try:
        return config.GitReport(conflicts=[], problem=None, written=generate(config.load(root), confirmed))
    except UnmarkedFileError:
        raise
    except CStarterError as error:
        return config.GitReport(conflicts=[], problem=str(error), written=[])


def _declare_driver(folder: Path) -> None:
    """Déclare le pilote de fusion dans la configuration locale du dépôt, qui n'est pas versionnée.
    Sa commande relance ce CStarter : son cstarter.exe s'il est installé, sinon
    l'interpréteur qui l'exécute et le dossier de son paquet. git la lance par son shell."""
    installed = executable()
    if installed is not None:
        command = f'"{installed.as_posix()}" merge-driver %O %A %B %L %P %X %Y'
    else:
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":  # l'interface graphique : git attend une console
            python = python.with_name("python.exe")
        package = Path(cstarter.__file__).resolve().parent.parent
        command = f'PYTHONPATH="{package.as_posix()}" "{python.as_posix()}" -m cstarter merge-driver %O %A %B %L %P %X %Y'
    vcs.set_config(folder, "merge.cstarter.name", "fusion des JSON de .cstarter/ par CStarter")
    vcs.set_config(folder, "merge.cstarter.driver", command)


def _ignored(project: config.Project) -> list[str]:
    """Les lignes de .gitignore : les fichiers générés, build/ où vont par défaut les .vcxproj et les
    sorties, les autres dossiers de sorties des targets, et .vs/ de Visual Studio."""
    outputs = sorted(
        {
            f"/{folder}/"
            for target in project.targets.values()
            for folder in (target.output.bin_dir, target.output.obj_dir)
            if folder.split("/")[0] != "build"
        }
    )
    return [
        "# Fichiers générés par CStarter depuis .cstarter/, et sorties de compilation",
        *_GENERATED,
        "/build/",
        *outputs,
        "# Visual Studio",
        ".vs/",
    ]


def _completed(path: Path, lines: list[str]) -> bytes | None:
    """Le contenu de path complété par celles de lines qui lui manquent, ou None s'il n'en manque
    aucune. Un fichier absent reçoit toutes les lignes ; un fichier existant, les lignes qui lui
    manquent, à la fin, précédées du premier commentaire, avec ses propres fins de ligne."""
    if not path.is_file():
        return ("\n".join(lines) + "\n").encode("utf-8")
    old = path.read_bytes()
    text = old.decode("utf-8-sig", errors="replace")
    present = {line.strip() for line in text.splitlines()}
    missing = [line for line in lines if not line.startswith("#") and line not in present]
    if not missing:
        return None
    comments = [line for line in lines if line.startswith("#")][:1]
    newline = "\r\n" if "\r\n" in text else "\n"
    separator = newline if text and not text.endswith("\n") else ""
    added = separator + (newline if text else "") + newline.join(comments + missing) + newline
    return old + added.encode("utf-8")


def _repository(root: Path) -> Path:
    """La racine du dépôt git qui contient le projet."""
    repository = vcs.toplevel(root)
    if repository is None:
        raise NotARepositoryError(
            t(f"{root} n'est dans aucun dépôt git : cstarter init le crée", f"{root} is in no git repository: cstarter init creates one")
        )
    return repository


def _branch_name(name: str) -> str:
    """Un nom de branche, qui ne doit pas passer pour une option de git."""
    if not name or name.startswith("-"):
        raise CStarterError(t(f"nom de branche invalide : « {name} »", f"invalid branch name: “{name}”"))
    return name


def _repository_name(url: str) -> str:
    """Le dossier que git clone crée par défaut : le dernier élément de url, sans .git."""
    name = url.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return name.removesuffix(".git") or "depot"


def _cstarter_first(path: str) -> tuple[bool, str]:
    return ("/.cstarter/" not in f"/{path}", path)
