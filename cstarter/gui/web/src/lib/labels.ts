// Les noms que l'interface donne aux valeurs du modèle. Des
// fonctions, et non des constantes : chaque rendu les lit dans la langue du moment.

import { t } from './i18n';

export const targetTypes = (): Record<string, string> => ({
  executable: t('Exécutable', 'Executable'),
  static_lib: t('Bibliothèque statique', 'Static library'),
  dynamic_lib: t('Bibliothèque dynamique', 'Dynamic library')
});

// Les mêmes, assez courts pour un contrôle segmenté.
export const targetKinds = (): Record<string, string> => ({
  executable: t('Exécutable', 'Executable'),
  static_lib: t('Statique', 'Static'),
  dynamic_lib: t('Dynamique', 'Dynamic')
});

export const subsystems = (): Record<string, string> => ({
  console: 'Console',
  windows: t('Fenêtrée', 'Windowed')
});

export const STANDARDS = ['c++14', 'c++17', 'c++20', 'c++23', 'c++latest'];

export const STANDARD_LABELS: Record<string, string> = {
  'c++14': 'C++14',
  'c++17': 'C++17',
  'c++20': 'C++20',
  'c++23': 'C++23',
  'c++latest': 'Latest'
};

export const cStandards = (): Record<string, string> => ({
  '': t('Défaut', 'Default'),
  c11: 'C11',
  c17: 'C17'
});

export const optimizations = (): Record<string, string> => ({
  disabled: t('Aucune', 'None'),
  min_size: t('Taille', 'Size'),
  max_speed: t('Vitesse', 'Speed'),
  full: t('Complète', 'Full')
});

export const warningLevels = (): Record<string, string> => ({
  Level1: '1',
  Level2: '2',
  Level3: '3',
  Level4: '4',
  EnableAllWarnings: t('Tous', 'All')
});

export const RUNTIMES: Record<string, string> = {
  MD: 'MD',
  MDd: 'MDd',
  MT: 'MT',
  MTd: 'MTd'
};

export const PLATFORMS = ['x64', 'x86', 'ARM64'];

export const GENERATORS: Record<string, string> = {
  vs2022: 'Visual Studio 2022',
  vs2026: 'Visual Studio 2026'
};

export const natures = (): Record<string, string> => ({
  header_only: 'Header-only',
  static_lib: t('Statique', 'Static'),
  dynamic_lib: t('Dynamique', 'Dynamic'),
  ambiguous: t('À préciser', 'To be specified')
});

export const builders = (): Record<string, string> => ({
  none: t('Headers seuls', 'Headers only'),
  cmake: 'CMake',
  premake: 'Premake',
  msbuild: 'MSBuild',
  manual: t('Manuel', 'Manual'),
  vcpkg: 'vcpkg',
  conan: 'conan'
});

export const importedFrom = (): Record<string, string> => ({
  manual: t('Créé vide', 'Created empty'),
  auto: 'Sources',
  cmake: 'CMake',
  premake: 'Premake',
  vcxproj: t('Solution Visual Studio', 'Visual Studio solution')
});

export const gitStates = (): Record<string, string> => ({
  M: t('Modifié', 'Modified'),
  A: t('Ajouté', 'Added'),
  D: t('Supprimé', 'Deleted'),
  R: t('Renommé', 'Renamed'),
  C: t('Copié', 'Copied'),
  T: t('Type changé', 'Type changed'),
  U: t('En conflit', 'In conflict'),
  '?': t('Nouveau', 'New')
});

// Ce que les lecteurs d'écran disent de l'état d'une paire de la matrice ou d'un outil.
export const statusWords = () => ({
  pending: t('En attente', 'Pending'),
  running: t('En cours', 'In progress'),
  done: t('Terminé', 'Completed'),
  failed: t('Échec', 'Failed'),
  cancelled: t('Annulé', 'Cancelled')
});
