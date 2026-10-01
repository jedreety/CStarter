"""Un générateur par cible, vs2022 d'abord. Il reçoit le modèle et les
dépendances résolues, et renvoie les fichiers à écrire. Il n'écrit jamais.

Ne dépend que de config/.
"""

from cstarter.generate import vs2022, vs2026

# La marque en tête de chaque fichier généré, que write.py contrôle.
MARK = vs2022.MARK

# La liste des générateurs, écrite en clair, par valeur de project.json. Chacun
# reçoit le projet et les entrées du cache résolues, par (nom, version).
GENERATORS = {"vs2022": vs2022.generate, "vs2026": vs2026.generate}

# Les extensions des fichiers que chaque générateur produit, où chercher les fichiers générés orphelins.
SUFFIXES = {"vs2022": vs2022.SUFFIXES, "vs2026": vs2026.SUFFIXES}

# Le toolset que chaque générateur écrit : generate prévient s'il manque, build choisit le MSBuild qui l'a.
TOOLSETS = {"vs2022": vs2022.TOOLSET, "vs2026": vs2026.TOOLSET}
