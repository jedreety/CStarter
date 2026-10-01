"""Le cadre de la fenêtre. La page dessine sa barre de titre et ses bords ;
Windows déplace, redimensionne et ancre la fenêtre (Aero Snap) comme une fenêtre ordinaire.

Un appui dans la barre ou sur un bord devient, dans le fil de la fenêtre, le clic non client que
Windows attend : la capture de la souris lui revient, et la boucle native de déplacement ou de
redimensionnement suit le pointeur. Une fenêtre sans cadre agrandie couvrirait la barre des tâches :
ses limites d'agrandissement suivent la zone de travail de l'écran qui la porte.
"""

import ctypes
from collections.abc import Callable
from ctypes import wintypes

import webview

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.SendMessageW.restype = ctypes.c_ssize_t
_user32.IsZoomed.argtypes = [wintypes.HWND]
_dwmapi = ctypes.WinDLL("dwmapi")
_dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
_WM_NCLBUTTONDOWN = 0x00A1
# Les codes de WM_NCHITTEST : la barre de titre, puis chaque bord et chaque coin.
_HITS = {
    "caption": 2,
    "left": 10,
    "right": 11,
    "top": 12,
    "topleft": 13,
    "topright": 14,
    "bottom": 15,
    "bottomleft": 16,
    "bottomright": 17,
}
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


class Chrome:
    def __init__(self, window: webview.Window) -> None:
        self._window = window

    @property
    def maximized(self) -> bool:
        """L'état de la fenêtre elle-même : Aero Snap l'agrandit aussi, sans passer par la page."""
        return bool(_user32.IsZoomed(self._hwnd()))

    def started(self, notify: Callable[[bool], None]) -> None:
        """La fenêtre existe : coins arrondis de Windows 11, limites d'agrandissement, et notify
        reçoit chaque passage de l'état agrandi à l'état normal."""
        corner = ctypes.c_int(_DWMWCP_ROUND)
        _dwmapi.DwmSetWindowAttribute(self._hwnd(), _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), 4)
        self._on_ui(self._fit)
        events = self._window.events
        events.maximized += lambda: notify(self.maximized)
        events.restored += lambda: notify(self.maximized)
        events.moved += lambda x, y: self._on_ui(self._fit)

    def press(self, edge: str) -> None:
        """Un appui de la souris dans la barre de titre ou sur un bord."""
        hit = _HITS[edge]

        def press() -> None:
            _user32.ReleaseCapture()
            _user32.SendMessageW(self._hwnd(), _WM_NCLBUTTONDOWN, hit, 0)

        self._on_ui(press)

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> None:
        if self.maximized:
            self._window.restore()
        else:
            self._window.maximize()

    def close(self) -> None:
        self._window.destroy()

    def _fit(self) -> None:
        """Les limites d'agrandissement : la zone de travail de l'écran, relative à cet écran."""
        from System.Drawing import Rectangle
        from System.Windows.Forms import Screen

        form = self._window.native
        screen = Screen.FromHandle(form.Handle)
        work, bounds = screen.WorkingArea, screen.Bounds
        form.MaximizedBounds = Rectangle(work.X - bounds.X, work.Y - bounds.Y, work.Width, work.Height)

    def _on_ui(self, action: Callable[[], None]) -> None:
        from System import Action

        self._window.native.BeginInvoke(Action(action))

    def _hwnd(self) -> int:
        return int(self._window.native.Handle.ToInt64())
