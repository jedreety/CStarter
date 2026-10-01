# CStarter

[English](README.md) · **Français**

CStarter est un gestionnaire de projets C et C++ pour Windows. Un projet se décrit une fois, dans un dossier `.cstarter/` de petits fichiers JSON, d'où CStarter génère sa solution Visual Studio, la compile par MSBuild et la lance. Il installe des bibliothèques dans un cache partagé et les lie à vos targets, convertit les projets CMake, Premake et Visual Studio, et travaille avec git. Il existe en application de bureau et en ligne de commande, en français et en anglais.

## Installation

Téléchargez `CStarter-<version>-setup.exe` depuis la [dernière version](https://github.com/jedreety/CStarter/releases/latest), puis lancez-le. CStarter s'installe pour l'utilisateur seul, dans `%LOCALAPPDATA%\Programs\CStarter`, sans droits d'administrateur. L'installeur peut ajouter `cstarter` au PATH, ajouter CStarter au menu Démarrer et à la recherche Windows, et créer un raccourci sur le bureau. CStarter fonctionne sous Windows 10 et 11 en 64 bits.

L'application cherche une version plus récente à son lancement. Elle la télécharge en arrière-plan et vérifie son empreinte SHA-256. Dès que Windows accepte le nouvel installeur, **Mettre à jour** apparaît dans la barre de titre : l'installeur remplace CStarter sans fenêtre et rouvre votre projet. `cstarter update` fait de même dans un terminal.

Pour désinstaller, passez par *Applications installées* dans les Paramètres de Windows. Une case supprime aussi les bibliothèques installées et les réglages (`%USERPROFILE%\.cstarter` et `%LOCALAPPDATA%\CStarter`). Les projets restent intacts.

Les versions ne sont pas encore signées (voir [Signature](#signature)). D'ici là, SmartScreen avertit au premier lancement de l'installeur, et sur un PC où Smart App Control est actif, Windows peut refuser une nouvelle version pendant un temps.

## Outils

CStarter pilote les outils que vous utilisez déjà. Compiler demande Visual Studio 2022, ou ses Build Tools, avec la charge de travail *Développement Desktop en C++*. CMake, Premake 5, vcpkg et conan 2 ne servent qu'aux bibliothèques et aux projets qui s'en servent. CStarter trouve les composants CMake et vcpkg de Visual Studio quand ils ne sont pas dans le PATH.

Quand des outils manquent, l'application les liste au premier lancement, puis sous **Outils** dans le menu de son logo, et installe par winget ceux que vous choisissez. Dans un terminal, en acceptant les fenêtres UAC, Visual Studio 2022 avec la charge C++, les outils ARM64, CMake et vcpkg :

    winget install --id Microsoft.VisualStudio.2022.Community --exact --source winget --accept-package-agreements --accept-source-agreements --override "--passive --wait --norestart --add Microsoft.VisualStudio.Workload.NativeDesktop --includeRecommended --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.VC.Tools.ARM64 --add Microsoft.VisualStudio.Component.VC.CMake.Project --add Microsoft.VisualStudio.Component.Vcpkg"

Puis, selon les usages, CMake, Premake 5 et conan 2 :

    winget install --id Kitware.CMake --exact --source winget
    winget install --id Premake.Premake.5.Beta --exact --source winget
    winget install --id JFrog.Conan --exact --source winget

## Premiers pas

Dans l'application, **Créer un projet** démarre un projet neuf, avec un premier target qui compile, ou la copie d'un modèle. **Convertir un projet existant** fait d'un projet CMake ou Premake, d'une solution Visual Studio ou d'un dossier de simples sources un projet CStarter. Ensuite, **Compiler** (Ctrl+B) et **Exécuter** (Ctrl+F5).

Dans un terminal, depuis un dossier qui contient les sources d'un programme :

    cstarter create
    cstarter build
    cstarter run

`create` fait du dossier la racine du projet. Il propose des targets d'après les sources et demande le type de chacun (Entrée garde la proposition), puis écrit `.cstarter/` et génère la solution. `build` et `run` prennent la première configuration et la première plateforme de la solution, sauf si `--config` et `--platform` en désignent d'autres.

## L'application

L'accueil propose de reprendre le dernier projet, d'en créer un, d'en ouvrir un, de convertir un projet existant, de cloner un dépôt, ou les **Bibliothèques** du cache, où l'on installe et supprime. À droite, le graphe du projet à reprendre, ou du récent sous le pointeur. En haut à droite, le compte GitHub que Git Credential Manager connaît, ou de quoi s'y connecter.

Dans un projet, à gauche, l'aperçu (le graphe du projet, qui se déplace en restant appuyé), les dépendances de chaque target, git, les réglages, puis chaque target. Les chemins se choisissent par l'icône de dossier de chaque champ, et le **+** d'une liste ouvre ce qu'on peut y ajouter : lier une bibliothèque à un target la lie à toutes ses configurations. **Toutes**, parmi les configurations d'un target, les compare côte à côte.

Les modifications restent en mémoire jusqu'à l'enregistrement (Ctrl+S). Ctrl+B compile la configuration et la plateforme choisies en haut, Ctrl+Maj+B chaque configuration pour chaque plateforme, et Ctrl+F5 compile puis exécute le target de démarrage, dans l'onglet **Programme** du panneau du bas. Ctrl+`` ` `` (Ctrl+² en AZERTY) ouvre le terminal intégré : PowerShell dans le dossier du projet, où `cstarter` lance ce même CStarter. **Ouvrir dans**, dans la barre de titre, ouvre le projet dans Visual Studio ou dans VS Code. Le menu du logo réunit la langue, les outils et **Rechercher une mise à jour**.

`cstarterw.exe DOSSIER` ouvre directement le projet de DOSSIER.

## Ligne de commande

Les commandes qui travaillent sur un projet chargent celui que désigne `-p DOSSIER`, placé avant la commande. Sans `-p`, CStarter remonte depuis le dossier courant jusqu'à `.cstarter/`. `create` et `detect` refusent `-p` : leur dossier se désigne par `--location`, le dossier courant par défaut. `cstarter COMMANDE --help` décrit chaque commande.

| Commandes | Rôle |
|---|---|
| `create`, `detect` | créer un projet, depuis les sources du dossier s'il y en a ; importer un dossier qui a déjà une configuration (voir [Import](#import)) |
| `generate`, `build`, `clean` | générer la solution ; générer puis compiler, `--all` pour toute la matrice ; supprimer fichiers générés et sorties |
| `run`, `get-program` | compiler puis lancer le target de démarrage, avec ses réglages de débogage ; afficher ce que `run` lance |
| `get-project`, `get-vcxprojs`, `get-vcxproj` | afficher le projet, la liste des targets, un target |
| `add-platform`, `remove-platform`, `set-startup`, `set-sln-output` | la solution : ses plateformes (x64, x86, ARM64), son target de démarrage, le dossier du `.sln` |
| `add-define`, `remove-define` | les defines globaux ; `--string` pour une chaîne C |
| `add-target`, `remove-target`, `rename-target` | les targets ; renommer suit les liens, le démarrage et les sorties par défaut |
| `add-config`, `remove-config`, `rename-config`, `add-config-define`, `remove-config-define` | les configurations d'un target ; renommer garde ce que chaque lien construit |
| `add-project-ref`, `remove-project-ref`, `set-project-ref` | les liens entre targets ; `--map Dist=Release`, que `set-project-ref` remplace |
| `set-source-dirs`, `add-include-dir`, `set-public-headers`, `set-vcxproj-dir`, `set-pch` | les sources et sorties d'un target, son en-tête précompilé |
| `analyze-dep`, `install-dep` | examiner une source sans rien compiler ; l'installer dans le cache, ou ajouter des plateformes à une entrée |
| `link-dep`, `unlink-dep` | lier une entrée du cache à une configuration d'un target ; la délier |
| `list-deps`, `get-dependency`, `get-dependencies`, `remove-dep` | lister le cache, afficher une entrée, lister celles du projet ; supprimer une entrée |
| `restore`, `vendor-dep`, `unvendor-dep`, `export-dep` | reconstruire ce qui manque au cache ; copier une entrée dans le projet, ou l'en retirer ; faire d'un target une entrée |
| `init`, `clone`, `status`, `add`, `commit`, `push`, `pull`, `branch`, `switch`, `merge`, `remote`, `log`, `diff`, `discard` | git (voir [git](#git)) |
| `language` | afficher la langue des messages, ou la choisir : `fr` ou `en` (voir [Langue](#langue)) |
| `update` | installer la dernière version publiée de CStarter |

`build --all` compile chaque configuration de la solution pour chaque plateforme, une paire après l'autre, puis donne le bilan de chacune.

Les autres réglages (runtime, optimisation, options libres) se modifient dans les JSON de `.cstarter/`, ou dans l'application. Les fichiers générés ne se modifient pas : la génération suivante les écrase, et supprime ceux que plus rien ne produit (après `remove-target`, par exemple). `add-config --copy-of` copie aussi les entrées liées et, vers une dépendance qui n'a pas la nouvelle configuration, celle que la copiée y construit.

## Dépendances

Le cache est dans `%USERPROFILE%\.cstarter\`, partagé par tous les projets. Une entrée est une seule configuration de build, pour une ou plusieurs plateformes : `fmt` en header-only, `spdlog_debug` en `MDd`, `spdlog_release` en `MD`.

La source est un dépôt `https://github.com/…` ou `https://gitlab.com/…` à un tag (`--tag`, résolu en commit), une archive `https://`, un dossier local, un port vcpkg (`vcpkg:PORT`, `--tag` donnant sa version exacte) ou un package conan (`conan:NOM/VERSION`). Le builder est `none` (header-only), `cmake`, `premake`, `msbuild` ou `manual` ; les sources vcpkg et conan ont leur propre builder, de même nom. Les options de chaque builder :

| Builder | Options |
|---|---|
| `cmake` | `--flag=-DOPTION=VALEUR` |
| `none` | `--flag include=DOSSIER` |
| `manual` | `--flag include=DOSSIER`, `--flag lib/x64=DOSSIER`, `--flag bin/x64=DOSSIER` |
| `msbuild`, `premake` | `--flag sln=FICHIER`, `--flag target=PROJET`, `--flag configuration=NOM`, `--flag include=DOSSIER` |
| `vcpkg` | `--flag linkage=static` ou `--flag linkage=dynamic` (défaut en `MD`) |
| `conan` | `--flag=-o=fmt/*:shared=True` |

`msbuild` et `premake` imposent le runtime de l'entrée et le toolset v143 à tous les projets de la solution. conan s'installe à part (voir [Outils](#outils)). Un package conan sans binaire pour les réglages demandés se construit depuis ses sources, avec le CMake de Visual Studio s'il n'y en a pas d'autre.

`install-dep` montre d'abord l'analyse, puis demande le système de build, sauf si `--build` le donne ; la source n'est téléchargée qu'une fois. Sans source, il ajoute les `--platform` à une entrée existante, avec sa recette. `--require NOM`, répétable, nomme une entrée que celle-ci attend : `link-dep` et `generate` avertissent quand la configuration ne la lie pas. `GITHUB_TOKEN` et `GITLAB_TOKEN`, s'ils existent, servent aux dépôts privés et à la limite de débit des API.

Dans l'application, **Installer une bibliothèque**, sur la page **Bibliothèques**, ne demande qu'un lien. Un dépôt GitHub ou GitLab propose ensuite ses versions, la dernière d'abord, et ses branches ; une branche s'installe au commit où elle en est. Après le téléchargement, CMake configure la source et montre tous ses paramètres, avec leur aide : seuls ceux qu'on change deviennent des options. L'installation construit une entrée NOM_runtime par runtime des configurations du projet ouvert (`fmt_mdd` pour Debug, `fmt_md` pour Release), pour les plateformes de sa solution ; un header-only n'en fait qu'une.

    cstarter install-dep lz4_md 1.10.0 vcpkg:lz4 --tag 1.10.0 --runtime MD
    cstarter install-dep zlib_md 1.3.1 conan:zlib/1.3.1 --runtime MD

Les entrées de `exemples/dependances/` s'installent ainsi :

    cstarter install-dep fmt 12.2.0 https://github.com/fmtlib/fmt --tag 12.2.0 --build none
    cstarter install-dep spdlog_debug 1.17.0 https://github.com/gabime/spdlog --tag v1.17.0 --build cmake --runtime MDd --platform x64 --platform ARM64 --flag=-DSPDLOG_BUILD_SHARED=ON --flag=-DSPDLOG_USE_STD_FORMAT=ON --flag=-DSPDLOG_BUILD_EXAMPLE=OFF
    cstarter install-dep spdlog_release 1.17.0 https://github.com/gabime/spdlog --tag v1.17.0 --build cmake --runtime MD --platform x64 --platform ARM64 --flag=-DSPDLOG_BUILD_SHARED=ON --flag=-DSPDLOG_USE_STD_FORMAT=ON --flag=-DSPDLOG_BUILD_EXAMPLE=OFF

Puis, dans un projet : `cstarter link-dep App Debug fmt 12.2.0`. La liaison refuse un runtime différent de celui de la configuration, une plateforme de la solution que l'entrée n'a pas, et deux entrées issues de la même source. La génération le vérifie de nouveau.

Une entrée ne déclare pas les defines et les options qu'elle attend de ses consommateurs : le projet les écrit lui-même. `exemples/dependances/` déclare ainsi `FMT_HEADER_ONLY`, `SPDLOG_COMPILED_LIB`, `SPDLOG_SHARED_LIB`, `SPDLOG_USE_STD_FORMAT`, et `/utf-8 /wd4251 /wd4275`. spdlog y utilise `std::format` : sa copie de fmt, liée à côté d'un autre fmt, ferait coexister deux fmt dans le même binaire.

## Portabilité

`dependencies.lock.json`, versionné, décrit chaque entrée liée : sa source exacte (commit, empreintes de l'archive et de son contenu, baseline de vcpkg, révision de conan) et sa recette. Sur une autre machine, `restore` reconstruit dans le cache ce qui y manque, empreinte vérifiée (une archive recompressée au contenu identique passe), puis `generate` et `build` suffisent. Une entrée locale (dossier, target exporté) ne se reconstruit pas ailleurs : `restore` la signale.

`vendor-dep NOM VERSION` copie une entrée dans `.cstarter/vendor/`, binaires compris. Le projet s'en sert alors sans le cache, sur toutes les machines. C'est le recours des entrées locales.

`export-dep TARGET CONFIG NOM VERSION` compile un target de type bibliothèque dans la configuration choisie, pour les plateformes de la solution (ou `--platform`), et en fait une entrée du cache : ses headers publics, ses `.lib`, ses `.dll` et leurs `.pdb`. Les entrées que lie cette configuration deviennent ses `requires`.

## Import

`cstarter detect [NOM] [--location DOSSIER]` lance tous les détecteurs : solution Visual Studio, CMake, Premake, `vcpkg.json`, `conanfile.txt`, git, et à défaut les sources seules. Il montre ce qu'il a reconnu et ce qu'il n'a pas su traduire, puis écrit `.cstarter/` après confirmation. Lire un `CMakeLists.txt` (par le File API de CMake) ou un `premake5.lua` (par `premake5 vs2022`, dans une copie) exécute le code du projet : CStarter demande l'accord d'abord. Les dépendances de `vcpkg.json` et de `conanfile.txt` s'installent dans le cache, une entrée par runtime (`lz4_mdd`, `lz4_md`, `lz4_mt`), liée à chaque target. Quand il ne trouve que des sources, il fait confirmer le type de chaque target, comme `create`. La suppression des anciens fichiers de configuration qu'il a traduits est proposée ensuite, jamais faite d'office. `cstarter generate` produit alors la solution.

Une entrée ne déclare pas les options qu'elle attend de ses consommateurs : fmt 11, par exemple, exige `/utf-8`. Le projet importé les ajoute lui-même dans ses JSON.

## Visual Studio 2026

`"generator": "vs2026"` dans `.cstarter/project.json` (ou le générateur, dans l'application) produit une solution pour Visual Studio 2026 : toolset `v145`, en-tête de Visual Studio 18. `generate` prévient quand aucune installation de Visual Studio n'a le toolset du générateur pour une plateforme de la solution ; `build` prend le MSBuild de la plus récente installation qui l'a.

## git

`init` crée le dépôt s'il n'existe pas, puis écrit `.gitignore` (les fichiers générés, `build/`, `.vs/` : ils se régénèrent) et `.gitattributes` (les JSON de `.cstarter/`, fusionnés par CStarter), et déclare le pilote de fusion dans `.git/config`. Il propose Git LFS pour les binaires vendorés. Un `.gitignore` existant n'est complété qu'après confirmation. Dans un dépôt cloné sans CStarter, `init` déclare le pilote.

    cstarter -p DOSSIER init
    cstarter -p DOSSIER add DOSSIER
    cstarter -p DOSSIER commit -m "Projet initial"
    cstarter clone URL DOSSIER

`remote origin URL` ajoute le remote, ou change son adresse. `log` montre les derniers commits, `diff CHEMIN` les modifications d'un fichier, et `discard CHEMIN` les annule après confirmation, sauf pour un fichier que le dernier commit n'a pas.

`clone` restaure les dépendances puis génère la solution. `pull`, `merge` et `switch` régénèrent la solution quand `.cstarter/` a changé. Le pilote fusionne les JSON de `.cstarter/` selon leur structure : deux targets, deux defines ou deux plateformes ajoutés de chaque côté se cumulent. Un vrai désaccord reste entre les marqueurs de git, autour du seul réglage en cause ; `status` le montre, puis `add` et `commit` terminent la fusion. Dans l'application, **Marquer résolu** prépare le fichier réparé.

## Langue

CStarter parle français ou anglais : l'application, ses messages et la ligne de commande. Le choix se fait par le menu du logo de l'application, ou par `cstarter language fr` ; il vaut pour les deux. Sans choix, CStarter suit la langue de Windows. MSBuild la suit par `VSLANG`. Ce que CStarter écrit dans un projet ne change pas avec la langue.

## Construire depuis les sources

CStarter n'utilise que Python 3.13 et sa bibliothèque standard. L'application demande aussi pywebview, et Node.js pour construire sa page une fois. Depuis la racine du dépôt :

    py -3.13 -m venv .venv
    .venv\Scripts\activate
    python -m pip install pywebview==6.2.1
    cd cstarter\gui\web
    npm ci
    npm run build

Ensuite, depuis la racine du dépôt, `python -m cstarter` est la ligne de commande et `python -m cstarter.gui [DOSSIER]` l'application.

### Construire l'installeur

PyInstaller s'installe dans le venv, figé par empreintes, et Inno Setup par winget :

    python -m pip install -r scripts/distribution/requirements.txt
    winget install --id JRSoftware.InnoSetup --exact --source winget --scope user

Puis, dans un dossier hors du dépôt :

    python scripts/distribution.py C:\cstarter-dist

Il construit la page, l'application avec `THIRD-PARTY-NOTICES.txt`, `CStarter-<version>-setup.exe` et `latest.json`. La version vient de `cstarter/__init__.py`. Un installeur construit ainsi ne sert qu'aux essais : les versions publiées sont construites par GitHub Actions à partir d'un tag `v<version>` ([`.github/workflows/publication.yml`](.github/workflows/publication.yml)), puis vérifiées et publiées par `scripts/publication.py`.

### Vérifier une modification

Pas de suite de tests : une modification se vérifie en comparant des générations. Avant la modification et après, chaque fois dans un dossier neuf hors du dépôt :

    python scripts/generations.py C:\cstarter-gen\avant
    python scripts/generations.py C:\cstarter-gen\apres
    git -c core.autocrlf=false diff --no-index C:\cstarter-gen\avant C:\cstarter-gen\apres

Un refactoring laisse les fichiers générés identiques à l'octet près, et un changement de comportement ne modifie que les lignes qu'il annonce. `exemples/dependances/` ne se génère que si ses entrées sont dans le cache. Les exemples `import-*` passent par `detect` en répondant oui à tout, sur leur copie : ils exigent CMake, premake5, vcpkg ou conan, et le réseau pour vcpkg et conan. Un exemple qui échoue est signalé, et le script génère les autres.

## Signature

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/) : la signature est offerte par SignPath.io, le certificat par SignPath Foundation. La [politique de signature](CODE_SIGNING.md) dit ce qui est signé, comment les versions sont construites et qui les approuve. La signature commence quand SignPath Foundation accepte le projet : les versions jusqu'à la 0.1.4 ne sont pas signées.

## Confidentialité

CStarter ne collecte aucune donnée et n'envoie aucune télémétrie. Au lancement de l'application, il demande à github.com si une version plus récente existe et, s'il y en a une, télécharge son installeur depuis GitHub. Tout le reste n'a lieu qu'à votre demande : le téléchargement des bibliothèques que vous installez (depuis GitHub, GitLab, vcpkg, conan ou une adresse que vous donnez), les opérations git sur les dépôts que vous choisissez, et l'installation par winget des outils que vous retenez.

## Licence

CStarter est publié sous [licence MIT](LICENSE). L'installeur livre aussi des composants d'autrui sous leur propre licence, que liste `THIRD-PARTY-NOTICES.txt` dans le dossier d'installation.
