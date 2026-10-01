"""La fusion des modèles partiels que renvoient les détecteurs.

Les targets viennent du premier système de build qui en propose, dans l'ordre de la liste des
détecteurs, et à défaut des sources seules. Les autres systèmes de build sont comparés au
premier : leurs désaccords deviennent des notes. Dépendances, notes, informations et lectures en
attente d'accord s'ajoutent. Les anciens fichiers de configuration aussi, mais seulement ceux
d'un détecteur qui a traduit des targets ou des dépendances : un fichier que l'import n'a pas
lu, faute d'accord ou sur un échec, n'est jamais proposé à la suppression.
"""

from cstarter.config.model import Detection, Solution, Target
from cstarter.language import t


def merge(detections: list[Detection]) -> Detection | None:
    """Le modèle fusionné, ou None si aucun détecteur n'a rien reconnu."""
    builds = [d for d in detections if d.imported_from not in (None, "auto") and d.targets]
    sources = [d for d in detections if d.imported_from == "auto" and d.targets]
    base = builds[0] if builds else sources[0] if sources else None
    notes = list(base.notes) if base else []
    for other in builds[1:]:
        notes += _disagreements(base, other)
    notes += [note for d in detections if not d.targets for note in d.notes]
    if builds and base.solution is not None:
        _public_headers(base.targets, base.solution)
    merged = Detection(
        targets=base.targets if base else [],
        notes=notes,
        imported_from=base.imported_from if base else None,
        name=base.name if base else None,
        solution=base.solution if base else None,
        requirements=[requirement for d in detections for requirement in d.requirements],
        pending=[item for d in detections for item in d.pending],
        info=[item for d in detections for item in d.info],
        files=sorted({path for d in detections if d.targets or d.requirements for path in d.files}),
    )
    if not (merged.targets or merged.requirements or merged.pending or merged.info or merged.notes):
        return None
    return merged


def _disagreements(base: Detection, other: Detection) -> list[str]:
    """Ce sur quoi other contredit base : les targets, leur type, leurs sources, leurs configurations."""
    mine = {target.name: target for target in base.targets}
    theirs = {target.name: target for target in other.targets}
    where = t(
        f"désaccord entre {base.imported_from} et {other.imported_from}",
        f"disagreement between {base.imported_from} and {other.imported_from}",
    )
    notes = []
    for name in sorted(mine.keys() | theirs.keys()):
        if name not in theirs:
            notes.append(t(f"{where} : {name} manque à {other.imported_from}", f"{where}: {name} missing from {other.imported_from}"))
        elif name not in mine:
            notes.append(
                t(
                    f"{where} : {name} manque à {base.imported_from}, il n'est pas repris",
                    f"{where}: {name} missing from {base.imported_from}, not kept",
                )
            )
        else:
            a, b = mine[name], theirs[name]
            if a.type != b.type:
                notes.append(t(f"{where} sur {name} : type {a.type} contre {b.type}", f"{where} on {name}: type {a.type} versus {b.type}"))
            if sorted(a.sources.files) != sorted(b.sources.files):
                notes.append(t(f"{where} sur {name} : les sources diffèrent", f"{where} on {name}: the sources differ"))
            left, right = ", ".join(c.name for c in a.configurations), ", ".join(c.name for c in b.configurations)
            if left != right:
                notes.append(
                    t(f"{where} sur {name} : configurations {left} contre {right}", f"{where} on {name}: configurations {left} versus {right}")
                )
    return notes


def _public_headers(targets: list[Target], solution: Solution) -> None:
    """Le dossier d'include qu'une bibliothèque partage avec tous ses consommateurs devient ses
    public_headers : la génération l'ajoute alors à chacun d'eux."""
    for library in targets:
        consumers = [t for t in targets if any(link.target == library.name for link in solution.depends_on(t.name))]
        if library.type == "executable" or library.public_headers is not None or not consumers:
            continue
        shared = [d for d in library.sources.include_dirs if all(d in t.sources.include_dirs for t in consumers)]
        if len(shared) == 1:
            library.public_headers = shared[0]
            for target in (library, *consumers):
                target.sources.include_dirs.remove(shared[0])
