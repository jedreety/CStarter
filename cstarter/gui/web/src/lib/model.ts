// Les données que l'API renvoie, telles que bridge.py les met en JSON.

export type Define = null | string | number | { string: string };

export interface Configuration {
  name: string;
  optimization: string;
  warning_level: string;
  runtime_library: string;
  debug_info: boolean;
  defines: Record<string, Define>;
  whole_program_opt: boolean;
  function_level_linking: boolean;
  link_time_code_gen: boolean;
  compiler_options: string[];
  linker_options: string[];
}

export interface DependencyRef {
  name: string;
  version: string;
}

export interface Target {
  name: string;
  type: string;
  subsystem: string;
  standard: string;
  c_standard: string | null;
  vcxproj_dir: string;
  public_headers: string | null;
  pch: { header: string; source: string } | null;
  sources: { mode: string; dirs: string[]; files: string[]; include_dirs: string[]; exclude: string[] };
  output: { bin_dir: string; obj_dir: string };
  debugger: { working_dir: string; arguments: string; environment: Record<string, string> };
  configurations: Configuration[];
  dependencies: Record<string, DependencyRef[]>;
  guid: string | null;
}

export interface Link {
  target: string;
  config_mapping: Record<string, string>;
}

export interface Solution {
  platforms: string[];
  startup_target: string | null;
  sln_output: string;
  global_defines: Record<string, Define>;
  targets: { name: string; depends_on: Link[] }[];
}

export interface Project {
  root: string;
  name: string;
  version: string;
  generator: string;
  imported_from: string;
  solution: Solution;
  targets: Record<string, Target>;
  vendored: DependencyRef[];
}

export interface View {
  root: string | null;
  project: Project | null;
  problem: string | null;
  dirty: boolean;
}

export interface Dependency {
  name: string;
  version: string;
  nature: string;
  source: {
    type: string;
    url: string | null;
    tag: string | null;
    commit: string | null;
    port: string | null;
    ref: string | null;
    original_path: string | null;
    resolvable: boolean;
  };
  build: { system: string; flags: string[]; platforms: string[]; runtime: string | null; toolset: string | null };
  libs: string[];
  requires: string[];
  created_at: string;
}

export interface CMakeOption {
  name: string;
  default: string;
  description: string;
  type: string;
  values: string[];
}

export interface AnalysisReport {
  source: Dependency['source'] & { sha256: string | null; baseline: string | null };
  build_systems: string[];
  nature: string;
  cmake_options: CMakeOption[];
  presets: string[];
  suggested_system: string;
  suggested_flags: string[];
  notes: string[];
  folders: Record<string, string[]>;
}

export interface Versions {
  source: string;
  tags: string[];
  latest: string | null;
  branches: { name: string; commit: string }[];
}

export interface RestoreReport {
  rebuilt: string[];
  present: string[];
  vendored: string[];
  failed: string[];
  warnings: string[];
}

export interface GitChange {
  path: string;
  index: string;
  worktree: string;
  conflicted: boolean;
  original: string | null;
}

export interface GitStatus {
  root: string;
  branch: string | null;
  upstream: string | null;
  ahead: number;
  behind: number;
  merging: boolean;
  changes: GitChange[];
}

export interface GitReport {
  conflicts: string[];
  problem: string | null;
  written: string[];
}

export interface Proposal {
  name: string;
  type: string;
  subsystem: string;
  folder: string;
  configurations: string[];
  links: string[];
}

export interface Recent {
  path: string;
  name: string;
}

export interface Prerequisite {
  name: string;
  present: boolean;
  package: string;
}

export interface Remote {
  name: string;
  url: string;
}

export interface Commit {
  hash: string;
  subject: string;
  author: string;
  date: string;
}

// Ce qu'Exécuter a lancé : run numérote les programmes console, qui passent par l'onglet
// Programme ; un programme fenêtré n'en a pas.
export interface Launch {
  run: number | null;
  windowed: boolean;
  target: string;
}

// La correspondance de configurations de la solution : la configuration de la solution,
// puis pour chaque target celle qu'il construit, ou rien.
export function solutionConfigurations(project: Project): string[] {
  const names = new Set<string>();
  Object.values(project.targets).forEach(t => t.configurations.forEach(c => names.add(c.name)));
  return [...names].sort();
}

export function targetOrder(project: Project): Target[] {
  return project.solution.targets.map(entry => project.targets[entry.name]).filter(Boolean);
}
