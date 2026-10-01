# La spécification PyInstaller de CStarter, que scripts/distribution.py
# lance : un seul dossier, deux exécutables. cstarter.exe, programme console, porte la ligne de
# commande, le pilote de fusion et le terminal intégré ; cstarterw.exe, programme fenêtré,
# l'interface et sa page construite.

import sys
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parents[1]
sys.path.insert(0, str(ROOT))
import cstarter  # noqa: E402

VERSION = cstarter.__version__
NUMBERS = (*(int(part) for part in VERSION.split(".")), 0)
ICON = str(Path(SPECPATH) / "cstarter.ico")


def version_info(name: str) -> VSVersionInfo:
    """La ressource de version : l'Explorateur et le Gestionnaire des tâches y lisent CStarter."""
    strings = StringTable(
        "040C04B0",
        [
            StringStruct("FileDescription", "CStarter"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", name),
            StringStruct("LegalCopyright", "Copyright (c) 2026 jedreety"),
            StringStruct("OriginalFilename", f"{name}.exe"),
            StringStruct("ProductName", "CStarter"),
            StringStruct("ProductVersion", VERSION),
        ],
    )
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
        kids=[StringFileInfo([strings]), VarFileInfo([VarStruct("Translation", [0x040C, 1200])])],
    )


# setuptools n'arrive que par les modules de cffi qui compilent des extensions : CStarter n'en
# compile aucune.
EXCLUDES = ["setuptools", "pkg_resources", "_distutils_hack"]
cli = Analysis([str(ROOT / "cstarter" / "__main__.py")], pathex=[str(ROOT)], excludes=EXCLUDES)
gui = Analysis(
    [str(ROOT / "cstarter" / "gui" / "__main__.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "cstarter" / "gui" / "web" / "dist"), "cstarter/gui/web/dist")],
    excludes=EXCLUDES,
)
# Ce qui ne sert jamais à CStarter, pour Windows x64 et WebView2 : la DLL x86 de clr_loader,
# l'interop du moteur Internet Explorer de pywebview, et son archive Android. Les dossiers
# runtimes/win-* de pywebview restent tous : il les ajoute au PATH à son chargement, et s'arrête
# s'il en manque un.
UNUSED = ("/x86/", "WebBrowserInterop.", "pywebview-android.jar")


def used(entries: list) -> list:
    return [entry for entry in entries if not any(part in entry[0].replace("\\", "/") for part in UNUSED)]
cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    exclude_binaries=True,
    name="cstarter",
    icon=ICON,
    version=version_info("cstarter"),
    console=True,
    upx=False,
)
gui_exe = EXE(
    PYZ(gui.pure),
    gui.scripts,
    exclude_binaries=True,
    name="cstarterw",
    icon=ICON,
    version=version_info("cstarterw"),
    console=False,
    upx=False,
)
COLLECT(cli_exe, gui_exe, used(cli.binaries), used(cli.datas), used(gui.binaries), used(gui.datas), name="CStarter", upx=False)
