"""Le terminal intégré : PowerShell dans une pseudo-console de Windows
(ConPTY), ouvert dans le dossier du projet. La même pseudo-console porte le programme qu'Exécuter
lance, avec les réglages de son débogueur.

La page l'affiche par xterm.js. Ce que l'utilisateur tape arrive par write ; ce que PowerShell écrit
repart vers la page, par paquets, depuis un fil qui vide la pseudo-console sans jamais attendre la
page. La commande cstarter y lance ce CStarter : son cstarter.exe installé, ou l'interpréteur de
l'interface.
"""

import codecs
import ctypes
import os
import shutil
import sys
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

import cstarter
from cstarter import api
from cstarter.language import t

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
_STARTF_USESTDHANDLES = 0x00000100
_INFINITE = 0xFFFFFFFF
_BATCH = 0.02


class _COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


_kernel32.CreatePipe.argtypes = [ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p, wintypes.DWORD]
_kernel32.CreatePseudoConsole.argtypes = [_COORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
_kernel32.CreatePseudoConsole.restype = ctypes.c_long
_kernel32.ResizePseudoConsole.argtypes = [ctypes.c_void_p, _COORD]
_kernel32.ResizePseudoConsole.restype = ctypes.c_long
_kernel32.ClosePseudoConsole.argtypes = [ctypes.c_void_p]
_kernel32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
_kernel32.UpdateProcThreadAttribute.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
_kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    ctypes.POINTER(_PROCESS_INFORMATION),
]
_kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]


class Terminal:
    def __init__(self, send: Callable[[str], None], ended: Callable[[int], None]) -> None:
        self._send = send
        self._ended = ended
        self._console = None
        self._input = None
        self._process = None
        self._pending: list[str] = []
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._console is not None

    def open(
        self, folder: Path, columns: int, rows: int, command: str | None = None, environment: dict[str, str] | None = None
    ) -> None:
        """Lance PowerShell dans folder, sur une pseudo-console de columns sur rows, ou command, une
        ligne de commande, avec environment. Un terminal déjà ouvert ne change que de taille."""
        if self.running:
            self.resize(columns, rows)
            return
        input_read, input_write = wintypes.HANDLE(), wintypes.HANDLE()
        output_read, output_write = wintypes.HANDLE(), wintypes.HANDLE()
        _check(_kernel32.CreatePipe(ctypes.byref(input_read), ctypes.byref(input_write), None, 0))
        _check(_kernel32.CreatePipe(ctypes.byref(output_read), ctypes.byref(output_write), None, 0))
        console = ctypes.c_void_p()
        result = _kernel32.CreatePseudoConsole(_COORD(columns, rows), input_read, output_write, 0, ctypes.byref(console))
        _kernel32.CloseHandle(input_read)
        _kernel32.CloseHandle(output_write)
        if result != 0:
            raise OSError(t(f"pseudo-console refusée, code {result & 0xFFFFFFFF:#x}", f"pseudo console refused, code {result & 0xFFFFFFFF:#x}"))
        size = ctypes.c_size_t()
        _kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attributes = ctypes.create_string_buffer(size.value)
        _check(_kernel32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)))
        _check(
            _kernel32.UpdateProcThreadAttribute(
                attributes, 0, _PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE, console, ctypes.sizeof(ctypes.c_void_p), None, None
            )
        )
        startup = _STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
        # Sans poignées standard désignées, PowerShell hériterait de celles de l'interface, détournées
        # vers l'onglet Sortie : nulles, ce sont celles de la pseudo-console.
        startup.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
        startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
        process = _PROCESS_INFORMATION()
        line = ctypes.create_unicode_buffer(command or _shell())
        block = ctypes.create_unicode_buffer("\0".join(f"{k}={v}" for k, v in (environment or os.environ).items()) + "\0\0")
        created = _kernel32.CreateProcessW(
            None,
            line,
            None,
            None,
            False,
            _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT,
            ctypes.cast(block, ctypes.c_void_p),
            str(folder),
            ctypes.byref(startup),
            ctypes.byref(process),
        )
        _kernel32.DeleteProcThreadAttributeList(attributes)
        if not created:
            _kernel32.ClosePseudoConsole(console)
            raise ctypes.WinError(ctypes.get_last_error())
        _kernel32.CloseHandle(process.hThread)
        self._console, self._input, self._process = console, input_write, process.hProcess
        threading.Thread(target=self._read, args=(output_read,), daemon=True).start()
        threading.Thread(target=self._forward, daemon=True).start()
        threading.Thread(target=self._wait, daemon=True).start()

    def write(self, data: str) -> None:
        if self._input is None:
            return
        raw = data.encode("utf-8")
        written = wintypes.DWORD()
        _kernel32.WriteFile(self._input, raw, len(raw), ctypes.byref(written), None)

    def resize(self, columns: int, rows: int) -> None:
        if self._console is not None:
            _kernel32.ResizePseudoConsole(self._console, _COORD(columns, rows))

    def close(self) -> None:
        """Arrête PowerShell, ou le programme ; la pseudo-console se ferme quand il a fini."""
        if self._process is not None:
            _kernel32.TerminateProcess(self._process, 0)

    def _read(self, output: wintypes.HANDLE) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        buffer = ctypes.create_string_buffer(65536)
        read = wintypes.DWORD()
        while _kernel32.ReadFile(output, buffer, len(buffer), ctypes.byref(read), None) and read.value:
            text = decoder.decode(buffer.raw[: read.value])
            with self._lock:
                self._pending.append(text)
        _kernel32.CloseHandle(output)

    def _forward(self) -> None:
        while self._console is not None or self._pending:
            time.sleep(_BATCH)
            with self._lock:
                text, self._pending = "".join(self._pending), []
            if text:
                try:
                    self._send(text)
                except Exception:  # la fenêtre se ferme
                    return

    def _wait(self) -> None:
        """PowerShell, ou le programme, a fini : la pseudo-console se ferme, ce qui termine la
        lecture, et ended reçoit son code de sortie."""
        _kernel32.WaitForSingleObject(self._process, _INFINITE)
        code = wintypes.DWORD()
        _kernel32.GetExitCodeProcess(self._process, ctypes.byref(code))
        console, self._console = self._console, None
        _kernel32.ClosePseudoConsole(console)
        _kernel32.CloseHandle(self._input)
        _kernel32.CloseHandle(self._process)
        self._input = self._process = None
        self._ended(ctypes.c_int32(code.value).value)


def _shell() -> str:
    """PowerShell 7 s'il est installé, sinon Windows PowerShell, avec une fonction cstarter qui lance
    ce CStarter : son cstarter.exe s'il est installé, sinon cet interpréteur, son paquet
    ajouté à PYTHONPATH le temps de la commande."""
    shell = shutil.which("pwsh") or "powershell.exe"

    def quoted(path: Path) -> str:  # une chaîne PowerShell entre apostrophes
        return "'" + str(path).replace("'", "''") + "'"

    installed = api.executable()
    if installed is not None:
        function = f"function cstarter {{ & {quoted(installed)} @args }}"
    else:
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        package = Path(cstarter.__file__).resolve().parent.parent
        function = (
            "function cstarter { $saved = $env:PYTHONPATH; "
            f"$env:PYTHONPATH = {quoted(package)}; "
            f"try {{ & {quoted(python)} -m cstarter @args }} finally {{ $env:PYTHONPATH = $saved }} }}"
        )
    return f'"{shell}" -NoLogo -NoExit -Command "{function}"'


def _check(succeeded: int) -> None:
    if not succeeded:
        raise ctypes.WinError(ctypes.get_last_error())
