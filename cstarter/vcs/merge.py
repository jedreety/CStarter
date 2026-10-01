"""Le pilote de fusion des JSON de .cstarter/ : une fusion à trois voies sur
la structure JSON, pas sur les lignes.

Deux ajouts différents dans une même liste se cumulent ; seul un vrai désaccord sur une même valeur
reste en conflit. Un élément de liste se reconnaît d'un côté à l'autre à son name, ou à son target
pour un lien, et à sa valeur dans une liste de textes. Un résultat sans conflit s'écrit comme
save_project l'écrit. Un conflit s'écrit entre les marqueurs de git, autour du plus
petit membre qui le contient : garder l'un des deux côtés donne un JSON valide.
"""

import json

from cstarter import config
from cstarter.language import t

_ABSENT = object()  # la valeur d'un côté qui n'a pas la clé ou l'élément


class _Conflict:
    """Deux valeurs que les deux côtés ont changées différemment. Aucune n'est _ABSENT : une
    suppression opposée à une modification remonte au membre qui les contient."""

    def __init__(self, ours: object, theirs: object) -> None:
        self.ours = ours
        self.theirs = theirs


def merge(
    base: bytes, ours: bytes, theirs: bytes, marker_size: int = 7, labels: tuple[str, str] = ("ours", "theirs")
) -> tuple[bytes, list[str]]:
    """Fusionne trois versions d'un JSON : base, l'ancêtre commun, vide quand les deux côtés ont
    ajouté le fichier, puis ours et theirs. Renvoie le résultat et les chemins JSON restés en
    conflit, vide si la fusion est propre. labels nomment les deux côtés dans les marqueurs."""
    labels = (labels[0] or "ours", labels[1] or "theirs")
    try:
        mine, other = _parse(ours), _parse(theirs)
        common = _parse(base) if base.strip() else _ABSENT
    except ValueError:  # un côté n'est pas du JSON : tout le fichier reste en conflit
        return _whole(ours, theirs, marker_size, labels), [t("le fichier entier, qui n'est pas du JSON", "the whole file, which is not JSON")]
    conflicts: list[str] = []
    merged = _merge(common, mine, other, "", conflicts)
    if not conflicts:
        return config.encode_json(merged), []
    lines: list[str] = []
    _render(merged, 0, "", "", lines, marker_size, labels)
    return ("\n".join(lines) + "\n").encode("utf-8"), conflicts


def _merge(base: object, ours: object, theirs: object, where: str, conflicts: list[str]) -> object:
    """La valeur fusionnée : _ABSENT si elle est supprimée, un _Conflict si les deux côtés
    s'opposent. where est son chemin JSON, pour nommer le conflit."""
    if _same(ours, theirs):
        return ours
    if _same(base, ours):
        return theirs
    if _same(base, theirs):
        return ours
    inner: list[str] = []
    merged = None
    if isinstance(ours, dict) and isinstance(theirs, dict):
        merged = _merge_dict(base if isinstance(base, dict) else {}, ours, theirs, where, inner)
    elif isinstance(ours, list) and isinstance(theirs, list):
        merged = _merge_list(base if isinstance(base, list) else [], ours, theirs, where, inner)
    if merged is None:
        conflicts.append(where or t("la racine", "the root"))
        return _Conflict(ours, theirs)
    conflicts += inner
    return merged


def _merge_dict(base: dict, ours: dict, theirs: dict, where: str, conflicts: list[str]) -> dict | None:
    """Les membres fusionnés un à un, ou None si l'un d'eux est supprimé d'un côté et modifié de
    l'autre : le conflit remonte alors à ce dictionnaire entier."""
    merged = {}
    for key in _order(list(base), list(ours), list(theirs)):
        value = _merge(base.get(key, _ABSENT), ours.get(key, _ABSENT), theirs.get(key, _ABSENT), f"{where}.{key}" if where else key, conflicts)
        if isinstance(value, _Conflict) and _ABSENT in (value.ours, value.theirs):
            return None
        if value is not _ABSENT:
            merged[key] = value
    return merged


def _merge_list(base: list, ours: list, theirs: list, where: str, conflicts: list[str]) -> list | None:
    """Les éléments fusionnés un à un, reconnus d'un côté à l'autre, ou None si la liste ne se
    fusionne qu'entière : éléments sans nom, doublons, suppression opposée à une modification."""
    identify = _identity([*base, *ours, *theirs])
    if identify is None:
        return None
    sides = [{identify(item): item for item in items} for items in (base, ours, theirs)]
    if any(len(keyed) != len(items) for keyed, items in zip(sides, (base, ours, theirs))):
        return None
    common, mine, other = sides
    merged = []
    for key in _order(list(common), list(mine), list(other)):
        value = _merge(common.get(key, _ABSENT), mine.get(key, _ABSENT), other.get(key, _ABSENT), f"{where}[{key}]", conflicts)
        if isinstance(value, _Conflict) and _ABSENT in (value.ours, value.theirs):
            return None
        if value is not _ABSENT:
            merged.append(value)
    return merged


def _identity(items: list) -> object:
    """Ce qui reconnaît un élément d'un côté à l'autre : name, ou target pour un lien, dans une liste
    d'objets ; la valeur dans une liste de textes ou de nombres. None si rien ne le permet."""
    if all(not isinstance(item, dict | list) for item in items):
        return lambda item: json.dumps(item, ensure_ascii=False)
    for field in ("name", "target"):
        if all(isinstance(item, dict) and isinstance(item.get(field), str) for item in items):
            return lambda item: item[field]
    return None


def _order(base: list, ours: list, theirs: list) -> list:
    """L'ordre des clés ou des éléments fusionnés : trié si les trois côtés le sont, comme
    save_project écrit les dictionnaires libres ; sinon celui de ours, où chaque ajout de theirs se
    place avant l'élément qui le suit chez theirs."""
    if all(side == sorted(side) for side in (base, ours, theirs)):
        return sorted({*base, *ours, *theirs})
    order = list(ours)
    for i, key in enumerate(theirs):
        if key not in order:
            following = next((k for k in theirs[i + 1 :] if k in order), None)
            order.insert(len(order) if following is None else order.index(following), key)
    return order + [key for key in base if key not in order]


def _same(a: object, b: object) -> bool:
    """a et b sont-ils la même valeur JSON ? true n'est pas 1, et l'ordre des clés ne compte pas."""
    if a is _ABSENT or b is _ABSENT:
        return a is b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[key], b[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _render(
    value: object, depth: int, prefix: str, comma: str, lines: list[str], size: int, labels: tuple[str, str]
) -> None:
    """Écrit value comme json.dumps(indent=2) : prefix, la clé d'un membre, avant sa première
    ligne, comma après sa dernière. Un conflit s'écrit entre les marqueurs, chaque côté avec sa clé
    et sa virgule."""
    pad = "  " * depth
    if isinstance(value, _Conflict):
        lines.append("<" * size + " " + labels[0])
        _render(value.ours, depth, prefix, comma, lines, size, labels)
        lines.append("=" * size)
        _render(value.theirs, depth, prefix, comma, lines, size, labels)
        lines.append(">" * size + " " + labels[1])
    elif isinstance(value, dict) and value:
        lines.append(pad + prefix + "{")
        for i, (key, item) in enumerate(value.items()):
            key_prefix = json.dumps(key, ensure_ascii=False) + ": "
            _render(item, depth + 1, key_prefix, "," if i < len(value) - 1 else "", lines, size, labels)
        lines.append(pad + "}" + comma)
    elif isinstance(value, list) and value:
        lines.append(pad + prefix + "[")
        for i, item in enumerate(value):
            _render(item, depth + 1, "", "," if i < len(value) - 1 else "", lines, size, labels)
        lines.append(pad + "]" + comma)
    else:
        lines.append(pad + prefix + json.dumps(value, ensure_ascii=False) + comma)


def _whole(ours: bytes, theirs: bytes, size: int, labels: tuple[str, str]) -> bytes:
    """Tout le fichier en conflit, quand l'un des côtés n'est pas du JSON."""
    sides = [data.decode("utf-8", errors="replace") for data in (ours, theirs)]
    sides = [text if text.endswith("\n") else text + "\n" for text in sides]
    text = f"{'<' * size} {labels[0]}\n{sides[0]}{'=' * size}\n{sides[1]}{'>' * size} {labels[1]}\n"
    return text.encode("utf-8")


def _parse(data: bytes) -> object:
    return json.loads(data.decode("utf-8-sig"))
