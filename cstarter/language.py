"""La langue des messages de CStarter : le français ou l'anglais.

Chaque message porte ses deux textes, t("français", "english"), et t rend celui de la langue
choisie. Le choix vit dans %LOCALAPPDATA%\\CStarter\\reglages.json : l'interface l'écrit, la ligne de
commande le lit, et les deux parlent la même langue. Sans choix, celle de Windows : le français
s'il est la langue de son interface, l'anglais sinon. MSBuild et le compilateur la suivent par
VSLANG, sauf si l'utilisateur l'a fixée lui-même.

Ce que CStarter écrit dans un projet ne dépend jamais de la langue : .cstarter/, les fichiers
générés, .gitignore et .gitattributes. Seuls les messages à l'utilisateur la suivent.

Importable depuis tout le paquet, comme errors.py.
"""

import ctypes
import json
import os
from pathlib import Path

from cstarter.errors import CStarterError

LANGUAGES = ("fr", "en")
# Le code de langue de Windows que VSLANG attend, pour chaque langue.
_VSLANG = {"fr": "1036", "en": "1033"}
_USER_VSLANG = os.environ.get("VSLANG")
_current: str | None = None


def language() -> str:
    """La langue des messages : celle que l'utilisateur a choisie, sinon celle de Windows."""
    global _current
    if _current is None:
        _current = _chosen() or _windows()
        _apply(_current)
    return _current


def set_language(code: str) -> None:
    """Choisit la langue des messages, pour l'interface comme pour la ligne de commande."""
    if code not in LANGUAGES:
        raise CStarterError(t(f"langue inconnue : « {code} » ({', '.join(LANGUAGES)})", f"unknown language: “{code}” ({', '.join(LANGUAGES)})"))
    global _current
    path = _settings()
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    settings["language"] = code
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _current = code
    _apply(code)


def t(fr: str, en: str) -> str:
    """Le texte de la langue choisie."""
    return en if language() == "en" else fr


def _chosen() -> str | None:
    try:
        code = json.loads(_settings().read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError):
        return None
    return code if code in LANGUAGES else None


def _windows() -> str:
    """Le français si c'est la langue de l'interface de Windows, l'anglais sinon."""
    try:
        identifier = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return "en"
    return "fr" if identifier & 0x3FF == 0x0C else "en"


def _apply(code: str) -> None:
    """Les programmes que CStarter lance, MSBuild et le compilateur, parlent sa langue."""
    if _USER_VSLANG is None:
        os.environ["VSLANG"] = _VSLANG[code]


def _settings() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home()), "CStarter", "reglages.json")
