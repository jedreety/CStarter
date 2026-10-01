"""Point d'entrée de l'interface graphique : python -m cstarter.gui [DOSSIER], ou cstarterw.exe
installé."""

import os
import sys

from cstarter.gui.app import main

# Installé, les programmes lancés démarrent en programmes indépendants, sans l'environnement de
# PyInstaller : sinon cstarter.exe, lancé depuis le terminal intégré, se croirait un sous-processus
# de l'interface.
if getattr(sys, "frozen", False):
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
sys.exit(main(sys.argv[1:]))
