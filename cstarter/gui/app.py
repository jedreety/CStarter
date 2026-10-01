"""La fenêtre de l'interface : pywebview, sans cadre, sur la page construite
dans web/dist/. Le moteur est WebView2, celui d'Edge, présent sur Windows 11.
"""

import os
import sys
from pathlib import Path

import webview

from cstarter.gui.bridge import Bridge
from cstarter.gui.output import Output
from cstarter.language import t

_PAGE = Path(__file__).resolve().parent / "web" / "dist" / "index.html"


def main(argv: list[str]) -> int:
    """Ouvre la fenêtre, sur le projet de argv[0] s'il est donné, et rend la main à sa fermeture."""
    if not _PAGE.is_file():
        print(t(
            "erreur : l'interface n'est pas construite : npm install puis npm run build, dans cstarter/gui/web",
            "error: the interface is not built: npm install then npm run build, in cstarter/gui/web",
        ), file=sys.stderr)
        return 1
    output = Output()
    output.start()
    bridge = Bridge(Path(argv[0]) if argv else None, output)
    window = webview.create_window(
        "CStarter",
        url=str(_PAGE),
        js_api=bridge,
        width=1320,
        height=840,
        min_size=(980, 640),
        frameless=True,
        easy_drag=False,
        background_color="#09090B",
    )
    bridge.attach(window)
    storage = Path(os.environ.get("LOCALAPPDATA", Path.home()), "CStarter", "interface", "webview")
    webview.start(bridge.started, http_server=True, private_mode=False, storage_path=str(storage))
    return 0
