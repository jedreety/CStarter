"""Un détecteur par source d'import. Il lit un dossier et renvoie un modèle
partiel, avec ce qu'il n'a pas su traduire. Il n'écrit jamais.

Ne dépend que de config/ et de toolchain/.
"""

from cstarter.detect import cmake, conan, git, premake, sources, vcpkg, vcxproj

# La liste des détecteurs, écrite en clair. Chacun reçoit le dossier, et l'accord de
# l'utilisateur pour exécuter le code du projet (CMake, Premake). L'ordre fixe la fusion : les
# targets viennent du premier système de build qui en propose, les sources seules en dernier.
DETECTORS = [premake.detect, cmake.detect, vcxproj.detect, vcpkg.detect, conan.detect, git.detect, sources.detect]
