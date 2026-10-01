"""Le cache de dépendances : metadata, registry, une source et un builder par fichier.
Il a sa propre écriture, dans %USERPROFILE%\\.cstarter\\.

Une source récupère une dépendance dans un dossier de travail : fetch(source, travail)
renvoie le dossier de ses sources et la source complétée (commit, empreinte). Un
builder en tire la disposition d'une entrée : build(sources, travail, entrée,
options, plateformes, runtime) renvoie le toolset utilisé, ou None.

Ne dépend que de config/ et de toolchain/.
"""

from cstarter.packages import cmake, conan, github, gitlab, local, local_project, manual, msbuild, none, premake, url, vcpkg

# La liste des sources et celle des builders, écrites en clair. Les sources vcpkg et
# conan délèguent la construction à leurs builders de même nom.
SOURCES = {
    "github": github.fetch,
    "gitlab": gitlab.fetch,
    "url": url.fetch,
    "local": local.fetch,
    "vcpkg": vcpkg.fetch,
    "conan": conan.fetch,
    "local_project": local_project.fetch,
}
BUILDERS = {
    "none": none.build,
    "cmake": cmake.build,
    "premake": premake.build,
    "msbuild": msbuild.build,
    "manual": manual.build,
    "vcpkg": vcpkg.build,
    "conan": conan.build,
}
