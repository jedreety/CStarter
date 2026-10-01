# CStarter

**English** · [Français](README.fr.md)

CStarter is a C and C++ project manager for Windows. You describe a project once, in a `.cstarter/` folder of small JSON files, and CStarter generates its Visual Studio solution, builds it with MSBuild and runs it. It installs libraries into a shared cache and links them to your targets, converts CMake, Premake and Visual Studio projects, and works with git. It comes as a desktop app and as a command line, in English and French.

## Install

Download `CStarter-<version>-setup.exe` from the [latest release](https://github.com/jedreety/CStarter/releases/latest) and run it. CStarter installs for the current user only, in `%LOCALAPPDATA%\Programs\CStarter`, without administrator rights. The installer can add `cstarter` to the PATH, add CStarter to the Start menu and Windows search, and create a desktop shortcut. CStarter runs on 64-bit Windows 10 and 11.

The app looks for a newer release when it starts. It downloads it in the background and checks its SHA-256 hash. Once Windows accepts the new installer, **Update** appears in the title bar: the installer replaces CStarter without a window and reopens your project. `cstarter update` does the same from a terminal.

To uninstall, use *Installed apps* in Windows Settings. A checkbox also removes the installed libraries and the settings (`%USERPROFILE%\.cstarter` and `%LOCALAPPDATA%\CStarter`). Projects are never touched.

Releases are not code-signed yet (see [Code signing](#code-signing)). Until they are, SmartScreen warns the first time you run the installer, and on a PC where Smart App Control is on, Windows may refuse a new release for a while.

## Tools

CStarter drives the tools you already use. Building needs Visual Studio 2022, or its Build Tools, with the *Desktop development with C++* workload. CMake, Premake 5, vcpkg and conan 2 are needed only by the libraries and projects that use them. CStarter finds the CMake and vcpkg components of Visual Studio when they are not in the PATH.

When tools are missing, the app lists them at first launch, and later under **Tools** in its logo menu, then installs the ones you pick through winget. From a terminal, accepting the UAC prompts, Visual Studio 2022 with the C++ workload, the ARM64 tools, CMake and vcpkg:

    winget install --id Microsoft.VisualStudio.2022.Community --exact --source winget --accept-package-agreements --accept-source-agreements --override "--passive --wait --norestart --add Microsoft.VisualStudio.Workload.NativeDesktop --includeRecommended --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.VC.Tools.ARM64 --add Microsoft.VisualStudio.Component.VC.CMake.Project --add Microsoft.VisualStudio.Component.Vcpkg"

Then, as needed, CMake, Premake 5 and conan 2:

    winget install --id Kitware.CMake --exact --source winget
    winget install --id Premake.Premake.5.Beta --exact --source winget
    winget install --id JFrog.Conan --exact --source winget

## Getting started

In the app, **Create a project** starts a new project with a first target that builds, or copies a template. **Convert an existing project** turns a CMake or Premake project, a Visual Studio solution or a folder of plain sources into a CStarter project. Then **Build** (Ctrl+B) and **Run** (Ctrl+F5).

From a terminal, in a folder that holds the sources of a program:

    cstarter create
    cstarter build
    cstarter run

`create` makes the folder the root of the project. It proposes targets from the sources and asks for the type of each one (Enter keeps the proposal), then writes `.cstarter/` and generates the solution. `build` and `run` use the first configuration and platform of the solution, unless `--config` and `--platform` say otherwise.

## The app

The home screen offers to resume the last project, create one, open one, convert an existing project, clone a repository, or manage the **Libraries** of the cache, where you install and remove them. On the right, it shows the graph of the project to resume, or of the recent one under the pointer. At the top right, it shows the GitHub account that Git Credential Manager knows, or a way to sign in.

Inside a project, the sidebar holds the overview (the project graph, which you can drag around), the dependencies of each target, git, the settings, then each target. Paths come from the folder icon of each field, and the **+** of a list opens what can be added to it: linking a library to a target links it to all of its configurations. Choosing **All** among the configurations of a target compares them side by side.

Changes stay in memory until you save (Ctrl+S). Ctrl+B builds the configuration and platform chosen at the top, Ctrl+Shift+B every configuration for every platform, and Ctrl+F5 builds then runs the startup target, in the **Program** tab of the bottom panel. Ctrl+`` ` `` (Ctrl+² on an AZERTY keyboard) opens the built-in terminal: PowerShell in the project folder, where `cstarter` runs this same CStarter. **Open in**, in the title bar, opens the project in Visual Studio or in VS Code. The logo menu holds the language, the tools and **Check for updates**.

`cstarterw.exe FOLDER` opens the project of FOLDER directly.

## Command line

Commands that work on a project load the one given by `-p FOLDER`, placed before the command. Without `-p`, CStarter looks for `.cstarter/` from the current folder upward. `create` and `detect` refuse `-p`: their folder is given by `--location`, the current folder by default. `cstarter COMMAND --help` describes each command.

| Commands | Purpose |
|---|---|
| `create`, `detect` | create a project, from the sources of the folder if any; import a folder that already has a build setup (see [Import](#import)) |
| `generate`, `build`, `clean` | generate the solution; generate then build, `--all` for every configuration and platform; remove generated files and build outputs |
| `run`, `get-program` | build, then run the startup target with its debugging settings; show what `run` launches |
| `get-project`, `get-vcxprojs`, `get-vcxproj` | show the project, the list of targets, a target |
| `add-platform`, `remove-platform`, `set-startup`, `set-sln-output` | the solution: its platforms (x64, x86, ARM64), its startup target, the folder of the `.sln` |
| `add-define`, `remove-define` | global defines; `--string` for a C string |
| `add-target`, `remove-target`, `rename-target` | targets; renaming follows links, the startup target and default outputs |
| `add-config`, `remove-config`, `rename-config`, `add-config-define`, `remove-config-define` | the configurations of a target; renaming keeps what each link builds |
| `add-project-ref`, `remove-project-ref`, `set-project-ref` | links between targets; `--map Dist=Release`, which `set-project-ref` replaces |
| `set-source-dirs`, `add-include-dir`, `set-public-headers`, `set-vcxproj-dir`, `set-pch` | the sources and outputs of a target, its precompiled header |
| `analyze-dep`, `install-dep` | examine a source without building anything; install it in the cache, or add platforms to an entry |
| `link-dep`, `unlink-dep` | link a cache entry to a configuration of a target; unlink it |
| `list-deps`, `get-dependency`, `get-dependencies`, `remove-dep` | list the cache, show an entry, list the entries of the project; remove an entry |
| `restore`, `vendor-dep`, `unvendor-dep`, `export-dep` | rebuild what the cache lacks; copy an entry into the project, or take it out; make a target an entry |
| `init`, `clone`, `status`, `add`, `commit`, `push`, `pull`, `branch`, `switch`, `merge`, `remote`, `log`, `diff`, `discard` | git (see [git](#git)) |
| `language` | show the language of the messages, or choose it: `fr` or `en` (see [Language](#language)) |
| `update` | install the latest release of CStarter |

`build --all` builds every configuration of the solution for every platform, one pair after the other, then reports on each.

Other settings (runtime library, optimization, free compiler options) are edited in the JSON files of `.cstarter/`, or in the app. Generated files are not meant to be edited: the next generation overwrites them, and deletes those that nothing produces any more (after `remove-target`, for instance). `add-config --copy-of` also copies the linked entries. When a target dependency lacks the new configuration, the link builds there the same configuration as the copied one does.

## Dependencies

The cache lives in `%USERPROFILE%\.cstarter\` and is shared by all projects. An entry is a single build configuration, for one or more platforms: `fmt` header-only, `spdlog_debug` built with `MDd`, `spdlog_release` with `MD`.

The source is a `https://github.com/…` or `https://gitlab.com/…` repository at a tag (`--tag`, resolved to a commit), an `https://` archive, a local folder, a vcpkg port (`vcpkg:PORT`, with `--tag` giving its exact version) or a conan package (`conan:NAME/VERSION`). The builder is `none` (header-only), `cmake`, `premake`, `msbuild` or `manual`; vcpkg and conan sources have their own builder, of the same name. The options of each builder:

| Builder | Options |
|---|---|
| `cmake` | `--flag=-DOPTION=VALUE` |
| `none` | `--flag include=FOLDER` |
| `manual` | `--flag include=FOLDER`, `--flag lib/x64=FOLDER`, `--flag bin/x64=FOLDER` |
| `msbuild`, `premake` | `--flag sln=FILE`, `--flag target=PROJECT`, `--flag configuration=NAME`, `--flag include=FOLDER` |
| `vcpkg` | `--flag linkage=static` or `--flag linkage=dynamic` (the default with `MD`) |
| `conan` | `--flag=-o=fmt/*:shared=True` |

`msbuild` and `premake` impose the runtime of the entry and the v143 toolset on every project of the solution. conan is installed separately (see [Tools](#tools)). A conan package without binaries for the requested settings is built from its sources, with the CMake of Visual Studio if there is no other.

`install-dep` shows the analysis first, then asks for the build system, unless `--build` gives it; the source is downloaded only once. Without a source, it adds the `--platform` values to an existing entry, with its recipe. `--require NAME`, repeatable, names an entry that this one expects: `link-dep` and `generate` warn when the configuration does not link it. `GITHUB_TOKEN` and `GITLAB_TOKEN`, when they are set, are used for private repositories and to raise API rate limits.

In the app, **Install a library**, on the **Libraries** page, asks only for a link. A GitHub or GitLab repository then offers its versions, the latest first, and its branches; a branch is installed at the commit it points to. After the download, CMake configures the source and shows all its parameters, with their help: only the ones you change become options. The installation builds one entry NAME_runtime per runtime of the configurations of the open project (`fmt_mdd` for Debug, `fmt_md` for Release), for the platforms of its solution; a header-only library makes only one.

    cstarter install-dep lz4_md 1.10.0 vcpkg:lz4 --tag 1.10.0 --runtime MD
    cstarter install-dep zlib_md 1.3.1 conan:zlib/1.3.1 --runtime MD

The entries of `exemples/dependances/` are installed this way:

    cstarter install-dep fmt 12.2.0 https://github.com/fmtlib/fmt --tag 12.2.0 --build none
    cstarter install-dep spdlog_debug 1.17.0 https://github.com/gabime/spdlog --tag v1.17.0 --build cmake --runtime MDd --platform x64 --platform ARM64 --flag=-DSPDLOG_BUILD_SHARED=ON --flag=-DSPDLOG_USE_STD_FORMAT=ON --flag=-DSPDLOG_BUILD_EXAMPLE=OFF
    cstarter install-dep spdlog_release 1.17.0 https://github.com/gabime/spdlog --tag v1.17.0 --build cmake --runtime MD --platform x64 --platform ARM64 --flag=-DSPDLOG_BUILD_SHARED=ON --flag=-DSPDLOG_USE_STD_FORMAT=ON --flag=-DSPDLOG_BUILD_EXAMPLE=OFF

Then, in a project: `cstarter link-dep App Debug fmt 12.2.0`. Linking refuses an entry whose runtime differs from the configuration's, an entry that lacks a platform of the solution, and two entries from the same source. Generation checks all of this again.

An entry does not declare the defines and options it expects from the projects that use it: the project writes them itself. `exemples/dependances/` thus declares `FMT_HEADER_ONLY`, `SPDLOG_COMPILED_LIB`, `SPDLOG_SHARED_LIB`, `SPDLOG_USE_STD_FORMAT`, and `/utf-8 /wd4251 /wd4275`. spdlog uses `std::format` there: its own copy of fmt, linked next to another fmt, would put two fmt in the same binary.

## Portability

`dependencies.lock.json`, committed with the project, describes each linked entry: its exact source (commit, hashes of the archive and of its contents, vcpkg baseline, conan revision) and its recipe. On another machine, `restore` rebuilds in the cache what is missing there, hashes checked (a recompressed archive with identical contents passes), then `generate` and `build` are enough. A local entry (a folder, an exported target) cannot be rebuilt elsewhere: `restore` reports it.

`vendor-dep NAME VERSION` copies an entry into `.cstarter/vendor/`, binaries included. The project then uses it without the cache, on every machine. This is the way out for local entries.

`export-dep TARGET CONFIG NAME VERSION` builds a library target in the chosen configuration, for the platforms of the solution (or `--platform`), and makes it a cache entry: its public headers, its `.lib` and `.dll` files and their `.pdb`. The entries that this configuration links become its `requires`.

## Import

`cstarter detect [NAME] [--location FOLDER]` runs every detector: Visual Studio solution, CMake, Premake, `vcpkg.json`, `conanfile.txt`, git and, failing those, plain sources. It shows what it recognized and what it could not translate, then writes `.cstarter/` after confirmation. Reading a `CMakeLists.txt` (through the CMake File API) or a `premake5.lua` (through `premake5 vs2022`, in a copy) runs the code of the project: CStarter asks for consent first. The dependencies of `vcpkg.json` and `conanfile.txt` are installed in the cache, one entry per runtime (`lz4_mdd`, `lz4_md`, `lz4_mt`), linked to each target. When it finds only sources, it has you confirm the type of each target, as `create` does. It then offers to delete the old configuration files it translated, and never does so on its own. `cstarter generate` then produces the solution.

An entry does not declare the options it expects from the projects that use it: fmt 11, for instance, requires `/utf-8`. The imported project adds them itself, in its JSON files.

## Visual Studio 2026

`"generator": "vs2026"` in `.cstarter/project.json` (or the generator, in the app) produces a solution for Visual Studio 2026: toolset `v145`, Visual Studio 18 header. `generate` warns when no installation of Visual Studio has the toolset of the generator for a platform of the solution; `build` uses the MSBuild of the most recent installation that has it.

## git

`init` creates the repository if there is none, then writes `.gitignore` (the generated files, `build/`, `.vs/`: they are regenerated) and `.gitattributes` (the JSON files of `.cstarter/`, merged by CStarter), and declares the merge driver in `.git/config`. It offers Git LFS for vendored binaries. An existing `.gitignore` is completed only after confirmation. In a repository cloned without CStarter, `init` declares the driver.

    cstarter -p FOLDER init
    cstarter -p FOLDER add FOLDER
    cstarter -p FOLDER commit -m "Initial project"
    cstarter clone URL FOLDER

`remote origin URL` adds the remote, or changes its address. `log` shows the last commits, `diff PATH` the changes of a file, and `discard PATH` undoes them after confirmation, except for a file that the last commit does not have.

`clone` restores the dependencies, then generates the solution. `pull`, `merge` and `switch` regenerate the solution when `.cstarter/` changed. The driver merges the JSON files of `.cstarter/` according to their structure: two targets, two defines or two platforms added on each side add up. A real disagreement stays between the markers of git, around the one setting at stake; `status` shows it, then `add` and `commit` finish the merge. In the app, **Mark resolved** stages the repaired file.

## Language

CStarter speaks English or French: the app, its messages and the command line. Choose it from the logo menu of the app, or with `cstarter language en`; the choice holds for both. Without a choice, CStarter follows the language of Windows. MSBuild follows it through `VSLANG`. What CStarter writes into a project does not change with the language.

## Building from source

CStarter needs Python 3.13 and its standard library only. The app also needs pywebview, and Node.js to build its page once. From the root of the repository:

    py -3.13 -m venv .venv
    .venv\Scripts\activate
    python -m pip install pywebview==6.2.1
    cd cstarter\gui\web
    npm ci
    npm run build

Then, from the root of the repository, `python -m cstarter` is the command line and `python -m cstarter.gui [FOLDER]` the app.

### Building the installer

PyInstaller goes in the venv, pinned with hashes, and Inno Setup comes from winget:

    python -m pip install -r scripts/distribution/requirements.txt
    winget install --id JRSoftware.InnoSetup --exact --source winget --scope user

Then, into a folder outside the repository:

    python scripts/distribution.py C:\cstarter-dist

It builds the page, the app with `THIRD-PARTY-NOTICES.txt`, `CStarter-<version>-setup.exe` and `latest.json`. The version comes from `cstarter/__init__.py`. An installer built this way is only for testing: releases are built by GitHub Actions from a `v<version>` tag ([`.github/workflows/publication.yml`](.github/workflows/publication.yml)), then checked and published by `scripts/publication.py`.

### Checking a change

There is no test suite: a change is checked by comparing generations. Before the change and after it, each time into a new folder outside the repository:

    python scripts/generations.py C:\cstarter-gen\before
    python scripts/generations.py C:\cstarter-gen\after
    git -c core.autocrlf=false diff --no-index C:\cstarter-gen\before C:\cstarter-gen\after

A refactoring leaves the generated files identical to the byte, and a change of behaviour changes only the lines it announces. `exemples/dependances/` is generated only if its entries are in the cache. The `import-*` examples go through `detect`, answering yes to everything, on their copy: they need CMake, premake5, vcpkg or conan, and the network for vcpkg and conan. An example that fails is reported, and the script generates the others.

## Code signing

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/). The [code signing policy](CODE_SIGNING.md) describes what gets signed, how releases are built and who approves them. Signing starts once SignPath Foundation accepts the project: releases up to 0.1.4 are not signed.

## Privacy

CStarter collects no data and sends no telemetry. When the app starts, it asks github.com whether a newer release exists, and if one does, downloads its installer from GitHub. Everything else happens only when you ask for it: downloading the libraries you install (from GitHub, GitLab, vcpkg, conan or an address you give), git operations on the repositories you choose, and installing the tools you pick through winget.

## License

CStarter is released under the [MIT license](LICENSE). The installer also ships third-party components under their own licenses, listed in `THIRD-PARTY-NOTICES.txt` in the installation folder.
