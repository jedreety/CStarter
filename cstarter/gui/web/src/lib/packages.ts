// Les paquets : les entrées du cache qu'une installation construit pour le projet, une par runtime
// de ses configurations (NOM_md, NOM_mdd…), ou une seule pour un header-only.
// Un target lie un paquet : chacune de ses configurations lie l'entrée de son runtime.

import type { Configuration, Dependency, DependencyRef, Project, Target } from './model';

export interface Package {
  key: string;
  name: string;
  version: string;
  entries: Dependency[];
}

// Un paquet lié : pour chaque configuration qui le lie, l'entrée qu'elle lie.
export interface Linked {
  key: string;
  name: string;
  version: string;
  refs: Record<string, DependencyRef>;
}

export type Call = [string, unknown[]];

const RUNTIME_SUFFIX = /^(.+)_(mdd|md|mtd|mt)$/i;

// Le nom du paquet d'une entrée : le sien, sans le suffixe de son runtime. Sans l'entrée elle-même,
// absente du cache, le suffixe suffit.
function packageName(name: string, runtime?: string | null): string {
  const match = RUNTIME_SUFFIX.exec(name);
  if (!match) return name;
  return runtime === undefined || runtime?.toLowerCase() === match[2].toLowerCase() ? match[1] : name;
}

export function packages(cache: Dependency[]): Package[] {
  const found = new Map<string, Package>();
  for (const entry of cache) {
    const name = packageName(entry.name, entry.build.runtime);
    const key = `${name}@${entry.version}`;
    if (!found.has(key)) found.set(key, { key, name, version: entry.version, entries: [] });
    found.get(key)!.entries.push(entry);
  }
  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version));
}

function packageKey(ref: DependencyRef, cache: Dependency[] | null): string {
  const entry = cache?.find(e => e.name === ref.name && e.version === ref.version);
  return `${packageName(ref.name, entry ? entry.build.runtime : undefined)}@${ref.version}`;
}

// L'entrée du paquet qui convient à la configuration : le header-only, sinon celle de son runtime.
function entryFor(pkg: Package, configuration: Configuration): Dependency | undefined {
  return pkg.entries.find(e => e.nature === 'header_only') ?? pkg.entries.find(e => e.build.runtime === configuration.runtime_library);
}

export function linkedPackages(target: Target, cache: Dependency[] | null): Linked[] {
  const found = new Map<string, Linked>();
  for (const [configuration, refs] of Object.entries(target.dependencies)) {
    for (const ref of refs) {
      const key = packageKey(ref, cache);
      if (!found.has(key)) found.set(key, { key, name: key.slice(0, key.indexOf('@')), version: ref.version, refs: {} });
      found.get(key)!.refs[configuration] = ref;
    }
  }
  return [...found.values()].sort((a, b) => a.key.localeCompare(b.key));
}

// Un paquet que le projet lie : les targets qui le lient, et les entrées qu'ils lient.
export interface Used {
  key: string;
  name: string;
  version: string;
  users: string[];
  refs: DependencyRef[];
}

export function projectPackages(project: Project, cache: Dependency[] | null): Used[] {
  const found = new Map<string, Used>();
  for (const target of Object.values(project.targets)) {
    for (const linked of linkedPackages(target, cache)) {
      if (!found.has(linked.key)) found.set(linked.key, { key: linked.key, name: linked.name, version: linked.version, users: [], refs: [] });
      const used = found.get(linked.key)!;
      used.users.push(target.name);
      for (const ref of Object.values(linked.refs)) {
        if (!used.refs.some(r => r.name === ref.name && r.version === ref.version)) used.refs.push(ref);
      }
    }
  }
  return [...found.values()].sort((a, b) => a.key.localeCompare(b.key));
}

// Lier le paquet aux configurations du target qui ne le lient pas encore. Celles dont le runtime n'a
// pas d'entrée restent de côté.
export function linkCalls(target: Target, pkg: Package, cache: Dependency[] | null, only?: string): { calls: Call[]; missing: string[] } {
  const linked = linkedPackages(target, cache).find(l => l.key === pkg.key);
  const calls: Call[] = [];
  const missing: string[] = [];
  for (const configuration of target.configurations) {
    if ((only && configuration.name !== only) || linked?.refs[configuration.name]) continue;
    const entry = entryFor(pkg, configuration);
    if (entry) calls.push(['link_dependency', [target.name, configuration.name, entry.name, entry.version]]);
    else missing.push(`${configuration.name} (${configuration.runtime_library})`);
  }
  return { calls, missing };
}

export function unlinkCalls(target: Target, linked: Linked, only?: string): Call[] {
  return Object.entries(linked.refs)
    .filter(([configuration]) => !only || configuration === only)
    .map(([configuration, ref]) => ['unlink_dependency', [target.name, configuration, ref.name]]);
}

// Après un changement de runtime, chaque paquet que la configuration lie passe à l'entrée du nouveau.
export function relinkCalls(target: Target, configuration: Configuration, cache: Dependency[] | null): { calls: Call[]; missing: string[] } {
  const all = packages(cache ?? []);
  const calls: Call[] = [];
  const missing: string[] = [];
  for (const ref of target.dependencies[configuration.name] ?? []) {
    const pkg = all.find(p => p.key === packageKey(ref, cache));
    const entry = pkg ? entryFor(pkg, configuration) : undefined;
    if (!pkg || entry?.name === ref.name) continue;
    if (!entry) {
      missing.push(pkg.name);
      continue;
    }
    calls.push(['unlink_dependency', [target.name, configuration.name, ref.name]]);
    calls.push(['link_dependency', [target.name, configuration.name, entry.name, entry.version]]);
  }
  return { calls, missing };
}
