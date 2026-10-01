"""Le pont entre la page et l'API.

La page appelle chaque méthode publique par window.pywebview.api, dans un fil à elle, et reçoit
{"ok": valeur} ou {"error": {...}}. Le projet ouvert vit ici, en mémoire : l'éditeur change ses
dataclasses, champ par champ ou par les fonctions de l'API, puis save_project le valide et l'écrit,
et revert le relit. Les opérations longues passent une à une ; leur sortie va à l'onglet Sortie, et
leurs étapes à la page par des événements. N'appelle que api/.
"""

import copy
import dataclasses
import functools
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import webview

from cstarter import api
from cstarter.errors import CStarterError, NotARepositoryError, UnmarkedFileError
from cstarter.gui.output import Output
from cstarter.gui.terminal import Terminal
from cstarter.gui.window import Chrome
from cstarter.language import language, set_language, t

# Les fonctions de l'API qui modifient le projet en mémoire, que la page appelle par leur nom.
_EDITS: dict[str, Callable] = {
    "add_platform": api.add_platform,
    "remove_platform": api.remove_platform,
    "set_startup_target": api.set_startup_target,
    "add_global_define": api.add_global_define,
    "remove_global_define": api.remove_global_define,
    "set_sln_output": api.set_sln_output,
    "add_project_reference": api.add_project_reference,
    "remove_project_reference": api.remove_project_reference,
    "set_project_reference": api.set_project_reference,
    "add_vcxproj": lambda project, name, type, subsystem="console": api.add_vcxproj(project, api.create_vcxproj(name, type, subsystem)),
    "remove_vcxproj": api.remove_vcxproj,
    "rename_vcxproj": api.rename_vcxproj,
    "add_configuration": api.add_configuration,
    "remove_configuration": api.remove_configuration,
    "rename_configuration": api.rename_configuration,
    "add_config_define": api.add_config_define,
    "remove_config_define": api.remove_config_define,
    "set_source_dirs": api.set_source_dirs,
    "add_include_dir": api.add_include_dir,
    "set_public_headers": api.set_public_headers,
    "set_vcxproj_dir": api.set_vcxproj_dir,
    "set_pch": api.set_pch,
    "link_dependency": api.link_dependency,
    "unlink_dependency": api.unlink_dependency,
    "vendor_dependency": api.vendor_dependency,
    "unvendor_dependency": api.unvendor_dependency,
}
# Les champs texte qui acceptent aussi null.
_OPTIONAL = {"c_standard", "public_headers", "startup_target"}
_RECENT = 12


def _answer(method: Callable) -> Callable:
    """{"ok": ce que method renvoie}, ou {"error": ...} pour une erreur que CStarter explique."""

    @functools.wraps(method)
    def wrapper(self, *args):
        try:
            return {"ok": _plain(method(self, *args))}
        except UnmarkedFileError as error:
            return {"error": {"kind": "unmarked", "message": str(error), "paths": error.paths}}
        except (CStarterError, OSError) as error:
            return {"error": {"kind": type(error).__name__, "message": str(error)}}

    return wrapper


class Bridge:
    def __init__(self, folder: Path | None, output: Output) -> None:
        self._folder = folder
        self._output = output
        self._window: webview.Window | None = None
        self._chrome: Chrome | None = None
        self._terminal: Terminal | None = None
        self._program: Terminal | None = None
        self._runs = 0
        self._lock = threading.RLock()
        self._busy = threading.Lock()
        self._root: Path | None = None
        self._project = None
        self._saved = None
        self._problem: str | None = None
        self._review = threading.Event()
        self._choice: tuple[str, list[str], list[str]] | None = None
        self._closing_confirmed = False
        self._installer: Path | None = None
        self._waiting: tuple[str, Path] | None = None  # la version téléchargée, et son installeur

    # La fenêtre

    def attach(self, window: webview.Window) -> None:
        self._window = window
        self._chrome = Chrome(window)

    def started(self) -> None:
        """La boucle de la fenêtre tourne : une fois la fenêtre affichée, son cadre, et la fermeture,
        qui propose d'abord d'enregistrer. pywebview lance cette fonction avant d'avoir créé la
        fenêtre native."""
        self._window.events.shown.wait()
        self._chrome.started(lambda maximized: self.emit("window", {"maximized": maximized}))
        self._window.events.closing += self._closing

    def _closing(self) -> bool:
        """Alt+F4 ou la barre des tâches ferment la fenêtre sans passer par la page : avec des
        modifications non enregistrées, la fermeture attend la réponse de l'utilisateur. Ce
        gestionnaire tourne dans le fil de la fenêtre, que la page ne peut rejoindre qu'après lui."""
        if self._closing_confirmed or not self._view()["dirty"]:
            for terminal in (self._terminal, self._program):
                if terminal is not None:
                    terminal.close()
            return True
        threading.Thread(target=self.emit, args=("close-requested", None), daemon=True).start()
        return False

    def emit(self, name: str, payload: object) -> None:
        """Un événement pour la page : window.cstarter.emit(name, payload)."""
        self._window.run_js(f"window.cstarter && window.cstarter.emit({json.dumps(name)}, {json.dumps(_plain(payload))})")

    @_answer
    def window_press(self, edge: str) -> None:
        self._chrome.press(edge)

    @_answer
    def window_minimize(self) -> None:
        self._chrome.minimize()

    @_answer
    def window_toggle_maximize(self) -> None:
        self._chrome.toggle_maximize()

    @_answer
    def window_close(self) -> None:
        """La page a réglé les modifications non enregistrées : la fenêtre se ferme."""
        self._closing_confirmed = True
        self._chrome.close()

    @_answer
    def window_state(self) -> dict:
        return {"maximized": self._chrome.maximized}

    # La session

    @_answer
    def start(self) -> dict:
        """La page est prête : la sortie du processus lui parvient désormais. Elle affiche d'abord le
        projet passé en argument, sinon l'accueil."""
        self._output.connect(lambda text: self.emit("output", text))
        if self._folder is not None and self._root is None:
            folder, self._folder = self._folder, None
            self._open(api.find_project(folder))
        return self._view()

    @_answer
    def recent(self) -> list[dict]:
        return [entry for entry in _read_recent() if Path(entry["path"], ".cstarter").is_dir()]

    @_answer
    def forget(self, path: str) -> list[dict]:
        entries = [entry for entry in _read_recent() if entry["path"] != path]
        _write_recent(entries)
        return entries

    @_answer
    def peek(self, path: str) -> object:
        """Le projet de path, lu sans être ouvert : l'accueil montre son graphe."""
        return api.get_project(Path(path))

    @_answer
    def github_account(self) -> str | None:
        return api.github_account()

    @_answer
    def github_login(self) -> str | None:
        """Git Credential Manager connecte un compte dans sa propre fenêtre ; l'accueil le montre ensuite."""
        with self._busy_guard():
            return api.github_login()

    @_answer
    def pick_folder(self) -> str | None:
        chosen = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return chosen[0] if chosen else None

    @_answer
    def pick(self, kind: str, start: str | None, multiple: bool, types: list[str]) -> list[str] | None:
        """Des dossiers (kind "folder") ou des fichiers choisis dans la boîte de Windows, relatifs à
        la racine du projet et à barres obliques. La boîte s'ouvre sur start, relatif
        lui aussi, ou sur son dossier ; types filtre les fichiers : "Sources (*.cpp;*.c)"."""
        root = self._require_root()
        opened = next((folder for folder in (root / start, (root / start).parent) if folder.is_dir()), root) if start else root
        dialog = webview.FileDialog.FOLDER if kind == "folder" else webview.FileDialog.OPEN
        chosen = self._window.create_file_dialog(dialog, directory=str(opened), allow_multiple=multiple, file_types=tuple(types))
        return [_relative(root, Path(path)) for path in chosen] if chosen else None

    @_answer
    def open(self, path: str) -> dict:
        self._open(api.find_project(Path(path)))
        return self._view()

    @_answer
    def close_project(self) -> dict:
        """Le terminal intégré se ferme avec le projet, celui du suivant s'ouvrira dans son dossier, et
        le programme lancé s'arrête."""
        with self._lock:
            self._root = self._project = self._saved = self._problem = None
        for terminal in (self._terminal, self._program):
            if terminal is not None:
                terminal.close()
        return self._view()

    @_answer
    def reload(self) -> dict:
        """Relit .cstarter/ depuis le disque : les modifications en mémoire sont abandonnées."""
        self._open(self._require_root())
        return self._view()

    # Créer, importer, cloner

    @_answer
    def propose(self, location: str) -> dict:
        """Les targets que les sources seules proposent pour create, et si le dossier a une
        configuration de build ou des dépendances que seul detect importe."""
        folder = Path(location)
        found = api.detect_sources(folder)
        if found is None:
            return {"targets": [], "notes": [], "importable": False}
        imported = api.detect(folder)
        importable = imported.imported_from != "auto" or bool(imported.pending or imported.requirements)
        return {"targets": _proposals(found), "notes": found.notes, "importable": importable}

    @_answer
    def create(self, location: str, name: str | None, types: dict[str, str]) -> dict:
        """Crée le projet dans location, avec le type confirmé de chaque target proposé."""
        folder = Path(location)
        found = api.detect_sources(folder)
        if found is not None:
            _confirm_types(found, types)
        project = api.create_project(folder, name or None, found)
        self._open(project.root)
        return self._view()

    @_answer
    def create_starter(self, location: str, name: str, type: str, subsystem: str) -> dict:
        """Crée le projet neuf name dans le dossier de même nom de location, avec son premier target et
        ses sources de départ."""
        project = api.create_starter(Path(location) / name, name, type, subsystem)
        self._open(project.root)
        return self._view()

    @_answer
    def create_from_template(self, template: str, location: str, name: str) -> dict:
        """Crée le projet name dans le dossier de même nom de location, en copie du projet de template."""
        with self._busy_guard():
            project = api.create_from_template(Path(template), Path(location) / name, name)
        self._open(project.root)
        return self._view()

    @_answer
    def inspect(self, location: str, execute: bool) -> dict:
        """Ce que l'import reconnaît dans location, sans rien écrire. Sans execute, CMake et
        Premake attendent dans pending l'accord de l'utilisateur."""
        found = api.detect(Path(location), execute)
        if found is None:
            return {"targets": [], "notes": [], "pending": [], "requirements": [], "info": [], "files": [], "imported_from": None}
        view = _plain(found)
        view["targets"] = _proposals(found)
        view["platforms"] = found.solution.platforms if found.solution else ["x64"]
        return view

    @_answer
    def import_folder(self, location: str, name: str | None, execute: bool, types: dict[str, str]) -> dict:
        """Importe location : écrit .cstarter/, et renvoie le projet et les anciens fichiers de
        configuration, dont la suppression se propose ensuite."""
        folder = Path(location)
        with self._busy_guard():
            found = api.detect(folder, execute)
            if found is None or not found.targets:
                raise CStarterError(t("rien à importer : aucun target reconnu", "nothing to import: no target recognized"))
            if found.imported_from == "auto":
                _confirm_types(found, types)
            project = api.create_project(folder, name or None, found)
        self._open(project.root)
        return {"view": self._view(), "files": found.files}

    @_answer
    def remove_old_files(self, paths: list[str]) -> list[str]:
        return api.remove_old_files(self._require(), paths)

    @_answer
    def clone(self, url: str, location: str) -> dict:
        with self._busy_guard():
            project, report = api.clone(url, Path(location))
        self._open(project.root)
        return {"view": self._view(), "restore": report}

    # Modifier le projet en mémoire

    @_answer
    def set(self, path: list, value: object) -> dict:
        """Change un champ du projet : path mène des dataclasses aux dictionnaires, et désigne un
        élément de liste par son nom. La nouvelle valeur a le type de l'ancienne."""
        with self._lock:
            node = self._require()
            *steps, last = path
            for step in steps:
                node = _child(node, step)
            _check(_child(node, last), value, last)
            _assign(node, last, value)
            return self._view()

    @_answer
    def edit(self, name: str, args: list) -> dict:
        """Une fonction de l'API qui modifie le projet en mémoire, parmi _EDITS."""
        with self._lock:
            _EDITS[name](self._require(), *args)
            return self._view()

    @_answer
    def batch(self, calls: list) -> dict:
        """Plusieurs fonctions de _EDITS, chacune [nom, arguments], dans l'ordre : toutes, ou aucune
        si l'une est refusée. Lier une dépendance à chaque configuration d'un target en demande une
        par configuration."""
        with self._lock:
            project = self._require()
            before = copy.deepcopy(project)
            try:
                for name, args in calls:
                    _EDITS[name](project, *args)
            except Exception:
                self._project = before
                raise
            return self._view()

    @_answer
    def save(self) -> dict:
        with self._lock:
            written = api.save_project(self._require())
            self._saved = copy.deepcopy(self._project)
            return {"written": written, "view": self._view()}

    # Générer et compiler

    @_answer
    def generate(self, confirmed: list[str]) -> list[str]:
        with self._busy_guard():
            return api.generate(self._require_saved(), confirmed)

    @_answer
    def build(self, configuration: str | None, platform: str | None, confirmed: list[str]) -> None:
        with self._busy_guard():
            api.build(self._require_saved(), configuration, platform, confirmed)

    @_answer
    def build_all(self, confirmed: list[str]) -> list:
        with self._busy_guard():
            progress = lambda c, p, ok: self.emit("build", {"configuration": c, "platform": p, "succeeded": ok})
            return api.build_all(self._require_saved(), confirmed, progress)

    @_answer
    def clean(self) -> list[str]:
        with self._busy_guard():
            return api.clean(self._require_saved())

    @_answer
    def open_solution(self) -> None:
        project = self._require_saved()
        solution = project.root / project.solution.sln_output / f"{project.name}.sln"
        if not solution.is_file():
            raise CStarterError(t("la solution n'est pas encore générée", "the solution is not generated yet"))
        os.startfile(solution)

    @_answer
    def open_vscode(self) -> None:
        api.open_in_vscode(self._require_saved())

    @_answer
    def reveal(self) -> None:
        os.startfile(self._require_root())

    # Les dépendances

    @_answer
    def cache(self) -> list:
        return api.list_all_dependencies()

    @_answer
    def linked(self) -> list:
        return api.get_dependencies(self._require_saved())

    @_answer
    def restore(self) -> object:
        with self._busy_guard():
            return api.restore(self._require_saved())

    @_answer
    def analyze(self, source: str, tag: str | None) -> object:
        with self._busy_guard():
            return api.analyze_dependency(source, tag or None)

    @_answer
    def versions(self, source: str) -> object:
        """Ce que la source propose d'installer : tags et branches d'un dépôt."""
        return api.list_versions(source)

    @_answer
    def install(self, name: str, version: str, source: str, tag: str | None, commit: str | None) -> list:
        """Installe la source pour le projet ouvert : ses plateformes, une entrée par runtime de ses
        configurations ; depuis l'accueil, pour un projet neuf. L'analyse va à la page avec le nom et
        la version, et la page répond par choose : le builder et ses options, ou None pour annuler."""

        def review(report: object) -> tuple[str, list[str], list[str]]:
            self._review.clear()
            self.emit("review", {"name": name, "version": version, "report": report})
            self._review.wait()
            if self._choice is None:
                raise _Cancelled(t("installation annulée : rien n'est entré dans le cache", "installation cancelled: nothing entered the cache"))
            return self._choice

        project = self._require() if self._root is not None else None
        with self._busy_guard():
            try:
                return api.install_for_project(project, name, version, source, tag or None, commit or None, review)
            except _Cancelled:
                return []

    @_answer
    def choose(self, system: str | None, flags: list[str], requires: list[str]) -> None:
        self._choice = (system, flags, requires) if system else None
        self._review.set()

    @_answer
    def add_platforms(self, name: str, version: str, platforms: list[str]) -> object:
        """Construit pour platforms une entrée du cache qui ne les a pas, avec sa recette."""
        with self._busy_guard():
            return api.install_dependency(name, version, platforms=platforms)

    @_answer
    def remove_dependency(self, name: str, version: str) -> None:
        api.remove_dependency(name, version, self._project)

    @_answer
    def export_dependency(self, target: str, configuration: str, name: str, version: str, confirmed: list[str]) -> object:
        with self._busy_guard():
            return api.export_as_dependency(self._require_saved(), target, configuration, name, version, (), confirmed)

    # git

    @_answer
    def git_status(self) -> object:
        """L'état du dépôt, ou None si le projet n'est dans aucun."""
        try:
            return api.status(self._require_root())
        except NotARepositoryError:
            return None

    @_answer
    def git_init(self, lfs: bool, confirmed: list[str]) -> list[str]:
        with self._busy_guard():
            return api.init(self._require_root(), lfs, confirmed)

    @_answer
    def git_commit(self, message: str, paths: list[str]) -> None:
        """Prépare puis valide les fichiers cochés. Pendant une fusion, git ne valide que l'index
        entier : les fichiers cochés sont préparés, puis tout est validé."""
        with self._busy_guard():
            root = self._require_root()
            status = api.status(root)
            # Un renommage se valide avec son ancien chemin, sinon seul l'ajout du nouveau partirait.
            paths = [*paths, *(c.original for c in status.changes if c.original and c.path in paths)]
            api.add(root, paths)
            api.commit(root, message, () if status.merging else paths)

    @_answer
    def git_push(self) -> None:
        with self._busy_guard():
            api.push(self._require_root())

    @_answer
    def git_pull(self, confirmed: list[str]) -> dict:
        with self._busy_guard():
            return self._after_git(api.pull(self._require_root(), confirmed))

    @_answer
    def git_branches(self) -> list[str]:
        return api.branch(self._require_root())

    @_answer
    def git_branch(self, name: str) -> list[str]:
        return api.branch(self._require_root(), name)

    @_answer
    def git_switch(self, name: str, create: bool, confirmed: list[str]) -> dict:
        with self._busy_guard():
            return self._after_git(api.switch(self._require_root(), name, create, confirmed))

    @_answer
    def git_merge(self, name: str, confirmed: list[str]) -> dict:
        with self._busy_guard():
            return self._after_git(api.merge(self._require_root(), name, confirmed))

    @_answer
    def git_remotes(self) -> list:
        return api.remote(self._require_root())

    @_answer
    def git_set_remote(self, name: str, url: str) -> list:
        return api.remote(self._require_root(), name, url)

    @_answer
    def git_log(self, count: int) -> list:
        return api.log(self._require_root(), count)

    @_answer
    def git_diff(self, path: str) -> str:
        return api.diff(self._require_root(), path)

    @_answer
    def git_discard(self, paths: list[str], confirmed: list[str]) -> dict:
        """Annule les modifications de paths, que l'utilisateur a confirmé : .cstarter/ a pu changer,
        le projet est relu."""
        with self._busy_guard():
            return self._after_git(api.discard(self._require_root(), paths, confirmed))

    @_answer
    def edit_conflict(self, path: str) -> None:
        """Ouvre un fichier en conflit dans un éditeur, pour le résoudre à la main. Seul un fichier
        que git montre en conflit s'ouvre, et toujours pour être modifié, jamais exécuté."""
        file = self._conflicted(path)
        try:
            os.startfile(file, "edit")
        except OSError:  # aucun éditeur associé à ce type de fichier
            subprocess.Popen(["notepad.exe", str(file)])

    @_answer
    def git_resolve(self, path: str) -> None:
        """Un fichier en conflit, réparé à la main, est préparé : git le tient alors pour résolu."""
        self._conflicted(path)
        api.add(self._require_root(), [path])

    def _conflicted(self, path: str) -> Path:
        """Le fichier path, que git doit montrer en conflit."""
        status = api.status(self._require_root())
        if path not in {change.path for change in status.changes if change.conflicted}:
            raise CStarterError(t(f"{path} n'est pas en conflit", f"{path} is not in conflict"))
        return status.root / path

    # La distribution

    @_answer
    def update_prepare(self) -> dict | None:
        """Télécharge en arrière-plan une version plus récente : {"version", "ready"}, sinon None.
        ready reste faux tant que Windows refuse de lancer son installeur ; la page rappelle alors
        update_prepare, qui ne fait plus que le lui redemander, sans réseau. Une vérification manquée,
        hors ligne par exemple, ne fait qu'une ligne dans l'onglet Sortie."""
        if api.update_disabled() is not None:
            return None
        try:
            first = self._waiting is None
            if first:
                update = api.check_update()
                if update is None:
                    return None
                self._waiting = (update.version, api.download_update(update))
            prepared = self._probe()
        except (CStarterError, OSError) as error:  # OSError : un fichier verrouillé, par un antivirus par exemple
            print(t(f"mise à jour de CStarter : {error}", f"CStarter update: {error}"), file=sys.stderr)
            return None
        if first and not prepared["ready"]:
            print(t(f"mise à jour de CStarter : {api.update_waiting(prepared['version'])}", f"CStarter update: {api.update_waiting(prepared['version'])}"), file=sys.stderr)
        return prepared

    def _probe(self) -> dict:
        """La version téléchargée, prête dès que Windows accepte de lancer son installeur."""
        version, installer = self._waiting
        if not api.installer_allowed(installer):
            return {"version": version, "ready": False}
        self._installer = installer
        return {"version": version, "ready": True}

    @_answer
    def update_install(self) -> None:
        """Lance l'installeur de la version prête, puis ferme la fenêtre : il relance l'interface,
        sur le projet ouvert. La page a réglé les modifications non enregistrées."""
        if self._installer is None:
            raise CStarterError(t("aucune mise à jour prête", "no update ready"))
        api.install_update(self._installer, relaunch=True, project=self._root)
        self._closing_confirmed = True
        self._chrome.close()

    @_answer
    def update_check(self) -> dict | None:
        """Comme update_prepare, sur demande : {"version", "ready"}, None si CStarter est à jour. Une
        vérification impossible, ou désactivée, remonte à la page."""
        reason = api.update_disabled()
        if reason is not None:
            raise CStarterError(reason)
        with self._busy_guard():
            update = api.check_update()
            if update is None:
                return None
            self._waiting = (update.version, api.download_update(update))
            return self._probe()

    @_answer
    def about(self) -> dict:
        """La version de CStarter et la langue de ses messages."""
        return {"version": api.VERSION, "language": language()}

    @_answer
    def choose_language(self, code: str) -> None:
        set_language(code)

    @_answer
    def prerequisites(self) -> list:
        return api.prerequisites()

    @_answer
    def install_prerequisite(self, name: str) -> list:
        """Installe un prérequis par winget, puis renvoie la liste à jour."""
        with self._busy_guard():
            api.install_prerequisite(name)
        return api.prerequisites()

    # Le terminal intégré

    @_answer
    def terminal_open(self, columns: int, rows: int) -> None:
        if self._terminal is None:
            self._terminal = Terminal(lambda text: self.emit("terminal", text), lambda code: self._closed_terminal())
        self._terminal.open(self._root or Path.home(), columns, rows)

    @_answer
    def terminal_input(self, data: str) -> None:
        if self._terminal is not None:
            self._terminal.write(data)

    @_answer
    def terminal_resize(self, columns: int, rows: int) -> None:
        if self._terminal is not None:
            self._terminal.resize(columns, rows)

    # Exécuter

    @_answer
    def run_program(self, configuration: str, platform: str, columns: int, rows: int, confirmed: list[str]) -> dict:
        """Compile, puis lance le target de démarrage avec les réglages de son débogueur : un programme
        console dans sa pseudo-console, que l'onglet Programme affiche et où l'on tape, un programme
        fenêtré seul. Un programme encore lancé s'arrête d'abord. Renvoie son numéro et s'il est fenêtré."""
        with self._busy_guard():
            project = self._require_saved()
            api.build(project, configuration, platform, confirmed)
            program = api.get_program(project, configuration, platform)
            api.check_program(program)
        environment = {**os.environ, **program.environment}
        command = [str(program.path), *program.arguments]
        if program.windowed:
            subprocess.Popen(command, cwd=program.working_dir, env=environment)
            return {"run": None, "windowed": True, "target": program.target}
        if self._program is not None:
            self._program.close()
        self._runs += 1
        run = self._runs
        self._program = Terminal(lambda text: self.emit("program", text), lambda code: self.emit("program-ended", {"run": run, "code": code}))
        self._program.open(program.working_dir, columns, rows, subprocess.list2cmdline(command), environment)
        return {"run": run, "windowed": False, "target": program.target}

    @_answer
    def program_input(self, data: str) -> None:
        if self._program is not None:
            self._program.write(data)

    @_answer
    def program_resize(self, columns: int, rows: int) -> None:
        if self._program is not None:
            self._program.resize(columns, rows)

    @_answer
    def program_stop(self) -> None:
        if self._program is not None:
            self._program.close()

    # L'état du projet

    def _open(self, root: Path) -> None:
        """Charge le projet de root. Un .cstarter/ illisible, pendant un conflit git par exemple,
        laisse le projet ouvert sans modèle : git reste utilisable pour le réparer."""
        with self._lock:
            self._root = root
            try:
                self._project = api.get_project(root)
                self._saved = copy.deepcopy(self._project)
                self._problem = None
            except CStarterError as error:
                self._project = self._saved = None
                self._problem = str(error)
        _remember(root, self._project.name if self._project else root.name)

    def _after_git(self, report: object) -> dict:
        """Après pull, switch ou merge, .cstarter/ a pu changer : le projet est relu."""
        self._open(self._require_root())
        return {"report": report, "view": self._view()}

    def _view(self) -> dict:
        with self._lock:
            return {
                "root": str(self._root) if self._root else None,
                "project": _plain(self._project),
                "problem": self._problem,
                "dirty": self._project is not None and self._project != self._saved,
            }

    def _require_root(self) -> Path:
        if self._root is None:
            raise CStarterError(t("aucun projet ouvert", "no project open"))
        return self._root

    def _require(self):
        self._require_root()
        if self._project is None:
            raise CStarterError(t(f".cstarter/ ne se lit pas : {self._problem}", f".cstarter/ cannot be read: {self._problem}"))
        return self._project

    def _require_saved(self):
        project = self._require()
        if project != self._saved:
            raise CStarterError(t("le projet a des modifications non enregistrées", "the project has unsaved changes"))
        return project

    def _busy_guard(self):
        if not self._busy.acquire(blocking=False):
            raise CStarterError(t("une opération est déjà en cours", "an operation is already running"))
        return _Release(self._busy)

    def _closed_terminal(self) -> None:
        self.emit("terminal-closed", None)


class _Cancelled(CStarterError):
    """La feuille des paramètres d'une installation refermée sans installer : rien n'échoue."""


class _Release:
    """Relâche le verrou des opérations longues à la fin du bloc with."""

    def __init__(self, lock: threading.Lock) -> None:
        self._lock = lock

    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        self._lock.release()


def _plain(value: object) -> object:
    """Une valeur de l'API en JSON : les dataclasses en objets, les chemins en texte."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _relative(root: Path, path: Path) -> str:
    """path relatif à root, à barres obliques. Un autre disque ne s'écrit pas en relatif."""
    try:
        return Path(os.path.relpath(path, root)).as_posix()
    except ValueError:
        raise CStarterError(t(f"{path} n'est pas sur le disque du projet", f"{path} is not on the project's drive")) from None


def _proposals(found: object) -> list[dict]:
    """Les targets d'une détection, pour la page : nom, type, sous-système, où sont ses sources,
    liens."""
    return [
        {
            "name": target.name,
            "type": target.type,
            "subsystem": target.subsystem,
            "folder": (target.sources.dirs or target.sources.files or [""])[0],
            "configurations": [c.name for c in target.configurations],
            "links": [link.target for link in found.solution.depends_on(target.name)] if found.solution else [],
        }
        for target in found.targets
    ]


def _confirm_types(found: object, types: dict[str, str]) -> None:
    """Le type que l'utilisateur confirme pour chaque target proposé ; un lien ne mène qu'à une
    bibliothèque : ceux vers un target devenu exécutable tombent, comme dans la ligne de commande."""
    for target in found.targets:
        target.type = types.get(target.name, target.type)
    executables = {target.name for target in found.targets if target.type == "executable"}
    for entry in found.solution.targets:
        entry.depends_on = [link for link in entry.depends_on if link.target not in executables]


def _child(node: object, key: object) -> object:
    """L'enfant key de node : un champ de dataclass, une clé de dictionnaire, un élément de liste
    désigné par son rang ou par son nom."""
    if dataclasses.is_dataclass(node):
        if not isinstance(key, str) or key not in {field.name for field in dataclasses.fields(node)}:
            raise CStarterError(t(f"champ inconnu : {key}", f"unknown field: {key}"))
        return getattr(node, key)
    if isinstance(node, dict):
        if key not in node:
            raise CStarterError(t(f"clé inconnue : {key}", f"unknown key: {key}"))
        return node[key]
    if isinstance(node, list):
        if isinstance(key, int):
            return node[key]
        for item in node:
            if getattr(item, "name", None) == key:
                return item
    raise CStarterError(t(f"élément introuvable : {key}", f"item not found: {key}"))


def _assign(node: object, key: object, value: object) -> None:
    if dataclasses.is_dataclass(node):
        setattr(node, key, value)
    elif isinstance(node, dict):
        node[key] = value
    elif isinstance(node, list) and isinstance(key, int):
        node[key] = value
    else:
        raise CStarterError(t(f"champ non modifiable : {key}", f"field cannot be changed: {key}"))


def _check(old: object, value: object, key: object) -> None:
    """La valeur d'un champ garde son type : la validation de save_project suppose les types de
    load, qui contrôle la forme de chaque JSON."""
    if isinstance(old, bool):
        valid = isinstance(value, bool)
    elif isinstance(old, str) or old is None:
        valid = isinstance(value, str) or (value is None and (old is None or key in _OPTIONAL))
    elif isinstance(old, list):
        valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
    elif isinstance(old, dict) and all(isinstance(item, str) for item in old.values()):
        valid = isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())
    else:
        valid = False
    if not valid:
        raise CStarterError(t(f"{key} : valeur de type inattendu", f"{key}: value of unexpected type"))


def _recent_file() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home()), "CStarter", "interface", "recents.json")


def _read_recent() -> list[dict]:
    try:
        entries = json.loads(_recent_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [entry for entry in entries if isinstance(entry, dict) and isinstance(entry.get("path"), str)]


def _write_recent(entries: list[dict]) -> None:
    path = _recent_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _remember(root: Path, name: str) -> None:
    """Les projets ouverts récemment, le dernier d'abord : l'accueil de l'interface les propose."""
    entries = [entry for entry in _read_recent() if entry["path"] != str(root)]
    _write_recent([{"path": str(root), "name": name}, *entries][:_RECENT])
