"""Point d'entrée : python -m cstarter, ou cstarter.exe installé."""

import os
import sys

from cstarter.cli import main

# Installé, les programmes lancés démarrent en programmes indépendants, sans l'environnement de
# PyInstaller : sinon cstarter.exe, lancé par l'un d'eux, se croirait son sous-processus.
if getattr(sys, "frozen", False):
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
sys.exit(main())
