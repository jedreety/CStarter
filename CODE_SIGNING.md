# Code signing policy / Politique de signature

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

## English

Published releases of CStarter, its executables, its uninstaller and its installer, are signed by SignPath Foundation. They are built by GitHub Actions from this repository's source code ([`.github/workflows/publication.yml`](.github/workflows/publication.yml)), and every signing request is approved by hand. Third-party libraries shipped inside the installer keep the signature, or the lack of one, that their authors gave them. Signing starts once SignPath Foundation accepts the project: versions 0.1.0 and 0.1.1 were published unsigned.

Team roles:

- Committers: [jedreety](https://github.com/jedreety)
- Reviewers: [jedreety](https://github.com/jedreety)
- Approvers: [jedreety](https://github.com/jedreety)

Privacy: CStarter collects no data and sends no telemetry. When its window starts, it asks github.com whether a newer release exists: GitHub sees that request, with the IP address and the user agent `cstarter`. Everything else happens only when the user asks for it: downloading the libraries they install (from GitHub, GitLab, vcpkg, conan or an address they give), git operations on the repositories they choose, and installing the tools they pick through winget.

## Français

Les versions publiées de CStarter, ses exécutables, son désinstalleur et son installeur, sont signées par SignPath Foundation. GitHub Actions les construit à partir des sources de ce dépôt ([`.github/workflows/publication.yml`](.github/workflows/publication.yml)), et chaque demande de signature est approuvée à la main. Les bibliothèques tierces livrées dans l'installeur gardent la signature, ou l'absence de signature, que leurs auteurs leur ont donnée. La signature commence quand SignPath Foundation accepte le projet : les versions 0.1.0 et 0.1.1 ont été publiées sans signature.

Rôles :

- Auteurs : [jedreety](https://github.com/jedreety)
- Relecteurs : [jedreety](https://github.com/jedreety)
- Approbateurs : [jedreety](https://github.com/jedreety)

Confidentialité : CStarter ne collecte aucune donnée et n'envoie aucune télémétrie. Au lancement de sa fenêtre, il demande à github.com si une version plus récente existe : GitHub voit cette requête, avec l'adresse IP et l'agent `cstarter`. Tout le reste n'a lieu qu'à la demande de l'utilisateur : le téléchargement des bibliothèques qu'il installe (depuis GitHub, GitLab, vcpkg, conan ou une adresse qu'il donne), les opérations git sur les dépôts qu'il choisit, et l'installation par winget des outils qu'il retient.
