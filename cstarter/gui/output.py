"""La sortie du processus, vers l'onglet Sortie de l'interface.

Ce qu'écrivent CStarter et les programmes qu'il lance (MSBuild, CMake, git, vcpkg, conan) passe
par les descripteurs 1 et 2 et par les poignées standard de Windows, dont les processus fils
héritent. Tous deviennent un tube. Un fil le vide sans jamais attendre la page ; un second envoie à
la page ce qu'il a lu, par paquets. Le terminal d'où l'interface est lancée en garde une copie.
"""

import ctypes
import msvcrt
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable

_STD_OUTPUT = -11
_STD_ERROR = -12
_BATCH = 0.05  # secondes entre deux envois à la page


class Output:
    def __init__(self) -> None:
        self._pending: list[str] = []
        self._lock = threading.Lock()
        self._send: Callable[[str], None] | None = None
        self._connected = threading.Event()
        self._console: int | None = None

    def start(self) -> None:
        """Détourne la sortie du processus vers le tube, avant que quoi que ce soit n'y écrive. Sans
        console, comme cstarterw.exe, le processus s'en donne d'abord une sans fenêtre."""
        if not _attached():
            _hidden_console()
            os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")  # personne ne pourrait y répondre
        try:
            self._console = os.dup(1)
        except OSError:  # lancé sans console
            self._console = None
        read, write = os.pipe()
        os.dup2(write, 1)
        os.dup2(write, 2)
        os.close(write)
        kernel32 = ctypes.windll.kernel32
        kernel32.SetStdHandle(_STD_OUTPUT, msvcrt.get_osfhandle(1))
        kernel32.SetStdHandle(_STD_ERROR, msvcrt.get_osfhandle(2))
        sys.stdout = open(1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
        sys.stderr = open(2, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
        threading.Thread(target=self._read, args=(read,), daemon=True).start()
        threading.Thread(target=self._forward, daemon=True).start()

    def connect(self, send: Callable[[str], None]) -> None:
        """La page est prête : send lui passe désormais le texte lu."""
        self._send = send
        self._connected.set()

    def _read(self, read: int) -> None:
        oem = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        waiting = b""
        while data := os.read(read, 65536):
            if self._console is not None:
                try:
                    os.write(self._console, data)
                except OSError:
                    self._console = None
            text, waiting = _decode(waiting + data, oem)
            with self._lock:
                self._pending.append(text)

    def _forward(self) -> None:
        self._connected.wait()
        while True:
            time.sleep(_BATCH)
            with self._lock:
                text, self._pending = "".join(self._pending), []
            if text:
                try:
                    self._send(text)
                except Exception:  # la fenêtre se ferme
                    return


def _attached() -> bool:
    """Le processus a-t-il une console ?"""
    processes = (ctypes.c_uint32 * 1)()
    return ctypes.windll.kernel32.GetConsoleProcessList(processes, 1) != 0


def _hidden_console() -> None:
    """Rejoint la console d'un cmd.exe lancé sans fenêtre, puis l'arrête : la console reste, sans
    fenêtre, et les programmes que CStarter lance s'y rattachent au lieu d'ouvrir chacun la leur.
    Se rattacher pendant que cmd.exe crée sa console échoue souvent : il écrit d'abord une ligne."""
    command = ["cmd.exe", "/d", "/q", "/k", "echo ok"]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW) as helper:
        helper.stdout.readline()
        ctypes.windll.kernel32.AttachConsole(helper.pid)
        helper.kill()


def _decode(data: bytes, oem: str) -> tuple[str, bytes]:
    """Le texte de data et les octets d'un caractère UTF-8 coupé en fin de lecture. Python et git
    écrivent en UTF-8 ; MSBuild dans la page de code OEM de la console, reconnue à son échec en UTF-8."""
    try:
        return data.decode("utf-8"), b""
    except UnicodeDecodeError as error:
        if error.reason == "unexpected end of data" and len(data) - error.start < 4:
            return data[: error.start].decode("utf-8", errors="replace"), data[error.start :]
        return data.decode(oem, errors="replace"), b""
