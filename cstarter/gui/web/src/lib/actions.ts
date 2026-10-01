// Ce que fait l'interface : chaque action appelle bridge.py, puis met l'état à jour.

import { ApiError, call, on } from './bridge';
import { askUnsaved, chooseBuild, confirmOverwrite, openPrerequisites } from './dialogs';
import { count, setLanguage, t, type Language } from './i18n';
import { output, program, terminal } from './log';
import type { AnalysisReport, Commit, Dependency, DependencyRef, GitReport, GitStatus, Launch, Prerequisite, Project, Recent, Remote, RestoreReport, View } from './model';
import { solutionConfigurations } from './model';
import { linkCalls, relinkCalls, unlinkCalls, type Call, type Linked, type Package } from './packages';
import { getState, setState, type Pair, type Tone } from './store';

let toastCounter = 0;
let runCounter = 0;

class Cancelled extends Error {}

// Les notifications

export function toast(title: string, tone: Tone = 'info', description?: string): void {
  const id = ++toastCounter;
  setState(s => ({ toasts: [...s.toasts, { id, title, tone, description }].slice(-4) }));
}

export function dismissToast(id: number): void {
  setState(s => ({ toasts: s.toasts.filter(t => t.id !== id) }));
}

function fail(error: unknown, title: string): void {
  if (error instanceof Cancelled) return;
  toast(title, 'danger', error instanceof Error ? error.message : String(error));
}

// Le démarrage

export async function boot(): Promise<void> {
  on('output', (text: string) => output.write(text));
  on('terminal', (text: string) => terminal.write(text));
  on('terminal-closed', () => {
    terminal.write('\r\n');
    setState({ terminalAlive: false });
  });
  on('program', (text: string) => program.write(text));
  on('program-ended', (payload: { run: number; code: number }) => programEnded(payload));
  on('window', (payload: { maximized: boolean }) => setState({ maximized: payload.maximized }));
  on('close-requested', () => requestClose());
  on('build', (payload: { configuration: string; platform: string; succeeded: boolean }) => advanceMatrix(payload));
  on('review', async (payload: { name: string; version: string; report: AnalysisReport }) => {
    const choice = await chooseBuild(payload.name, payload.version, payload.report);
    await call('choose', choice?.system ?? null, choice?.flags ?? [], choice?.requires ?? []);
  });
  window.addEventListener('keydown', shortcuts);
  try {
    // La langue d'abord : tout ce que la page et bridge.py écrivent ensuite la suit.
    const about = await call<{ version: string; language: Language }>('about');
    setLanguage(about.language);
    setState({ language: about.language, version: about.version });
    const [view, recent, frame] = await Promise.all([
      call<View>('start'),
      call<Recent[]>('recent'),
      call<{ maximized: boolean }>('window_state')
    ]);
    setState({ booted: true, recent, maximized: frame.maximized });
    showView(view, 'overview', true);
    if (view.root) {
      refreshGit();
      refreshCache();
    }
    prepareUpdate();
    checkPrerequisites();
    refreshGithub();
  } catch (error) {
    setState({ booted: true });
    fail(error, t('Ouverture impossible', 'Cannot open'));
  }
}

function shortcuts(event: KeyboardEvent): void {
  if (!event.ctrlKey) return;
  const view = getState().view;
  if (event.key === 's' || event.key === 'S') {
    event.preventDefault();
    (document.activeElement as HTMLElement | null)?.blur(); // le champ en cours se valide en perdant le focus
    edits.then(() => getState().view?.dirty && save());
  } else if ((event.key === 'b' || event.key === 'B') && view?.project) {
    event.preventDefault();
    if (event.shiftKey) buildAll();
    else buildSelected();
  } else if (event.key === 'F5') {
    event.preventDefault(); // sans quoi WebView2 recharge la page
    if (view?.project) runSelected();
  } else if (event.key === '`' || event.code === 'Backquote') {
    event.preventDefault();
    toggleTerminal();
  }
}

export function toggleTerminal(): void {
  setState(s => ({ panel: { ...s.panel, open: !(s.panel.open && s.panel.tab === 'terminal'), tab: 'terminal' } }));
}

// La langue de l'interface et des messages de bridge.py, que la ligne de commande partage.
export async function chooseLanguage(next: Language): Promise<void> {
  try {
    await call('choose_language', next);
    setLanguage(next);
    setState({ language: next });
  } catch (error) {
    fail(error, t('Langue refusée', 'Language refused'));
  }
}

// Le projet ouvert. reread vaut vrai quand le projet vient du disque (ouverture, relecture, git) :
// les contrôles qui gardent leur propre état repartent alors de ses valeurs.

function showView(view: View, page?: string, reread = false): void {
  if (reread) setState(s => ({ epoch: s.epoch + 1 }));
  setState(s => {
    const project = view.project;
    let next = page ?? s.page;
    if (next.startsWith('target:') && !project?.targets[next.slice(7)]) next = 'overview';
    if (!project && view.root) next = 'git';
    const configurations = project ? solutionConfigurations(project) : [];
    const pair =
      project && s.pair && configurations.includes(s.pair.configuration) && project.solution.platforms.includes(s.pair.platform)
        ? s.pair
        : project && configurations.length
          ? { configuration: configurations[0], platform: project.solution.platforms[0] }
          : null;
    return { view, page: next, pair };
  });
}

export function navigate(page: string): void {
  setState({ page });
  if (page === 'git') refreshGit();
  if (page === 'deps' || page === 'overview' || page.startsWith('target:')) refreshCache();
}

export async function refreshRecent(): Promise<void> {
  setState({ recent: await call<Recent[]>('recent') });
}

// Ouvre le projet de path, ou du dossier au-dessus. Sans projet, l'erreur remonte à l'appelant quand
// il la demande : l'accueil propose alors de créer ou d'importer.
export async function openProject(path: string, rethrow = false): Promise<boolean> {
  try {
    adopt(await call<View>('open', path), 'overview');
    output.clear();
    setState({ matrix: null, run: null });
    return true;
  } catch (error) {
    if (rethrow) throw error;
    fail(error, t('Aucun projet CStarter ici', 'No CStarter project here'));
    return false;
  }
}

export async function forgetRecent(path: string): Promise<void> {
  setState({ recent: await call<Recent[]>('forget', path) });
}

// Un projet récent, lu sans l'ouvrir : l'accueil montre son graphe.
export async function peekProject(path: string): Promise<Project | null> {
  try {
    return await call<Project>('peek', path);
  } catch {
    return null;
  }
}

// Créer un projet : neuf, avec son premier target et ses sources de départ, ou en copie d'un
// modèle. Il s'ouvre, et sa solution se génère.
export async function createStarter(location: string, name: string, type: string, subsystem: string): Promise<void> {
  try {
    created(await call<View>('create_starter', location, name, type, subsystem));
  } catch (error) {
    fail(error, t('Création impossible', 'Cannot create'));
    return;
  }
  await generate();
}

export async function createFromTemplate(template: string, location: string, name: string): Promise<void> {
  const view = await operation('create', t('Créer', 'Create'), name, () => call<View>('create_from_template', template, location, name), false);
  if (!view) return;
  created(view);
  await generate();
}

function created(view: View): void {
  adopt(view, 'overview');
  setState({ home: 'start' });
  toast(t('Projet créé', 'Project created'), 'success', view.project?.name);
}

// Le compte GitHub que Git Credential Manager connaît : la barre de titre de l'accueil le montre.
async function refreshGithub(): Promise<void> {
  try {
    setState({ github: await call<string | null>('github_account') });
  } catch {
    setState({ github: null });
  }
}

// Git Credential Manager connecte un compte dans sa propre fenêtre : CStarter ne voit jamais son jeton.
export async function githubLogin(): Promise<void> {
  const account = await operation('git', 'GitHub', '', () => call<string | null>('github_login'), false);
  if (account === undefined) return;
  setState({ github: account });
  if (account) toast(t('Connecté à GitHub', 'Signed in to GitHub'), 'success', account);
}

export async function closeProject(): Promise<void> {
  if (!(await settleUnsaved())) return;
  terminal.clear(); // le terminal du projet suivant s'ouvrira dans son dossier
  program.clear();
  showView(await call<View>('close_project'), 'overview', true);
  setState(s => ({ git: undefined, cache: null, matrix: null, run: null, program: null, panel: { ...s.panel, tab: s.panel.tab === 'program' ? 'output' : s.panel.tab } }));
  refreshRecent();
}

export async function requestClose(): Promise<void> {
  if (!(await settleUnsaved())) return;
  await call('window_close');
}

// Enregistrer ou abandonner les modifications en mémoire. Renvoie faux si l'utilisateur annule.
async function settleUnsaved(): Promise<boolean> {
  await edits;
  if (!getState().view?.dirty) return true;
  const choice = await askUnsaved();
  if (choice === 'save') return save();
  if (choice === 'discard') {
    await revert();
    return true;
  }
  return false;
}

export function adopt(view: View, page?: string): void {
  showView(view, page, true);
  setState({ git: undefined });
  refreshGit();
  refreshRecent();
  refreshCache();
}

// Modifier le projet en mémoire. Un champ se valide en perdant le focus, souvent par le clic qui
// enregistre ou compile : ces actions attendent d'abord les modifications en vol.

let edits: Promise<unknown> = Promise.resolve();

function track<T>(pending: Promise<T>): Promise<T> {
  edits = edits.then(() => pending).catch(() => undefined);
  return pending;
}

export async function setField(path: (string | number)[], value: unknown): Promise<boolean> {
  try {
    showView(await track(call<View>('set', path, value)));
    return true;
  } catch (error) {
    fail(error, t('Valeur refusée', 'Value refused'));
    return false;
  }
}

export async function edit(name: string, ...args: unknown[]): Promise<boolean> {
  try {
    showView(await track(call<View>('edit', name, args)));
    return true;
  } catch (error) {
    fail(error, t('Modification refusée', 'Change refused'));
    return false;
  }
}

// Plusieurs modifications d'un coup : toutes, ou aucune.
export async function batch(calls: Call[]): Promise<boolean> {
  if (!calls.length) return true;
  try {
    showView(await track(call<View>('batch', calls)));
    return true;
  } catch (error) {
    fail(error, t('Modification refusée', 'Change refused'));
    return false;
  }
}

// Renommer un target : la page qui le montrait suit son nouveau nom.
export async function renameTarget(name: string, next: string): Promise<void> {
  const page = getState().page;
  if ((await edit('rename_vcxproj', name, next)) && page === `target:${name}`) setState({ page: `target:${next}` });
}

export async function save(): Promise<boolean> {
  await edits;
  try {
    const result = await call<{ written: string[]; view: View }>('save');
    showView(result.view);
    toast(t('Enregistré', 'Saved'), 'success');
    refreshGit();
    return true;
  } catch (error) {
    fail(error, t('Enregistrement refusé', 'Save refused'));
    return false;
  }
}

export async function revert(): Promise<void> {
  showView(await call<View>('reload'), undefined, true);
}

async function ensureSaved(): Promise<boolean> {
  await edits;
  return !getState().view?.dirty || save();
}

// Des chemins choisis dans la boîte de Windows, relatifs à la racine du projet.
export async function pickPaths(kind: 'folder' | 'file', start?: string, multiple = false, types: string[] = []): Promise<string[] | null> {
  try {
    return await call<string[] | null>('pick', kind, start ?? null, multiple, types);
  } catch (error) {
    fail(error, t('Chemin refusé', 'Path refused'));
    return null;
  }
}

export async function pickFolder(): Promise<string | null> {
  return call<string | null>('pick_folder');
}

// Les opérations longues : une à la fois, leur sortie dans l'onglet Sortie. kind nomme l'opération
// pour sa durée attendue, name la montre.

export async function operation<T>(
  kind: string,
  name: string,
  argument: string,
  action: (confirmed: string[]) => Promise<T>,
  openPanel = true
): Promise<T | undefined> {
  if (getState().busy) {
    toast(t('Une opération est déjà en cours', 'An operation is already running'));
    return undefined;
  }
  const id = ++runCounter;
  setState(s => ({
    busy: true,
    run: { id, kind, name, argument, status: 'running' },
    panel: openPanel ? { ...s.panel, open: true, tab: 'output' } : s.panel
  }));
  output.section(`${name} ${argument}`);
  try {
    const result = await confirming(action);
    setState({ busy: false, run: { id, kind, name, argument, status: 'done' } });
    return result;
  } catch (error) {
    setState({ busy: false, run: { id, kind, name, argument, status: 'error' } });
    fail(error, t(`${name} : échec`, `${name}: failed`));
    return undefined;
  }
}

// Un fichier existant sans la marque de CStarter n'est écrasé qu'après confirmation.
async function confirming<T>(action: (confirmed: string[]) => Promise<T>): Promise<T> {
  try {
    return await action([]);
  } catch (error) {
    if (error instanceof ApiError && error.kind === 'unmarked') {
      if (!(await confirmOverwrite(error.paths))) throw new Cancelled();
      return await action(error.paths);
    }
    throw error;
  }
}

async function generateQuietly(): Promise<string[] | undefined> {
  return operation('generate', t('Générer', 'Generate'), getState().view?.project?.generator ?? '', c => call<string[]>('generate', c), false);
}

export async function generate(): Promise<void> {
  if (!(await ensureSaved())) return;
  const written = await generateQuietly();
  if (written) {
    toast(written.length ? t('Solution générée', 'Solution generated') + ` · ${count(written.length, ['fichier', 'fichiers'], ['file', 'files'])}` : t('Solution à jour', 'Solution up to date'), 'success');
  }
}

// Visual Studio ouvre toujours la solution de ce que .cstarter/ contient : elle est générée d'abord.
export async function openInVisualStudio(): Promise<void> {
  if (!(await ensureSaved())) return;
  if ((await generateQuietly()) === undefined) return;
  try {
    await call('open_solution');
  } catch (error) {
    fail(error, t('Visual Studio ne s’ouvre pas', 'Visual Studio does not open'));
  }
}

export function selectPair(configuration: string, platform: string): void {
  setState({ pair: { configuration, platform } });
}

export async function buildSelected(): Promise<void> {
  const pair = getState().pair;
  if (pair) await build(pair.configuration, pair.platform);
}

export async function build(configuration: string, platform: string): Promise<void> {
  if (!(await ensureSaved())) return;
  const done = await operation('build', 'MSBuild', `${configuration} · ${platform}`, c => call('build', configuration, platform, c).then(() => true));
  if (done) toast(t('Compilation réussie', 'Build succeeded'), 'success', `${configuration} · ${platform}`);
}

export async function buildAll(): Promise<void> {
  const project = getState().view?.project;
  if (!project || !(await ensureSaved())) return;
  const pairs: Pair[] = solutionConfigurations(project).flatMap(configuration =>
    project.solution.platforms.map(platform => ({ configuration, platform, status: 'pending' as const }))
  );
  if (pairs.length) pairs[0].status = 'running';
  // La matrice ne paraît qu'une fois l'opération lancée, et son échec l'efface.
  let started = false;
  const results = await operation('build', 'MSBuild', t('toute la matrice', 'the whole matrix'), c => {
    started = true;
    setState({ matrix: pairs });
    return call<[string, string, boolean][]>('build_all', c);
  });
  if (!results) {
    if (started) setState({ matrix: null });
    return;
  }
  const failed = results.filter(result => !result[2]).length;
  if (failed) toast(t(`${failed} sur ${results.length} en échec`, `${failed} of ${results.length} failed`), 'danger');
  else toast(t('Toute la matrice compile', 'The whole matrix builds'), 'success', count(results.length, ['paire', 'paires'], ['pair', 'pairs']));
}

function advanceMatrix(done: { configuration: string; platform: string; succeeded: boolean }): void {
  setState(s => {
    if (!s.matrix) return {};
    const matrix = s.matrix.map(p =>
      p.configuration === done.configuration && p.platform === done.platform
        ? { ...p, status: done.succeeded ? ('done' as const) : ('failed' as const) }
        : p
    );
    const next = matrix.find(p => p.status === 'pending');
    if (next) next.status = 'running';
    return { matrix };
  });
}

// Exécuter : compiler, puis lancer le target de démarrage. Un programme console tourne dans
// l'onglet Programme, où l'on tape ; un programme fenêtré s'ouvre seul.

export async function runSelected(): Promise<void> {
  const pair = getState().pair;
  if (pair) await runProgram(pair.configuration, pair.platform);
}

export async function runProgram(configuration: string, platform: string): Promise<void> {
  if (!(await ensureSaved())) return;
  const launch = await operation('build', t('Exécuter', 'Run'), `${configuration} · ${platform}`, c => {
    // Le programme écrit dès son lancement, avant la réponse : son onglet repart de zéro avant.
    program.clear();
    program.section(`${configuration} · ${platform}`);
    return call<Launch>('run_program', configuration, platform, program.grid.cols, program.grid.rows, c);
  });
  if (!launch) return;
  if (launch.run === null) {
    toast(t(`${launch.target} lancé`, `${launch.target} started`), 'success', `${configuration} · ${platform}`);
    return;
  }
  setState(s => ({ program: { run: launch.run!, target: launch.target, code: null }, panel: { ...s.panel, open: true, tab: 'program' } }));
}

export async function stopProgram(): Promise<void> {
  await call('program_stop');
}

function programEnded(payload: { run: number; code: number }): void {
  const current = getState().program;
  if (!current || current.run !== payload.run) return; // un programme remplacé par le suivant
  program.write(`\r\n\x1b[38;2;142;140;255m●\x1b[0m ${t('Terminé, code', 'Exited, code')} ${payload.code}\r\n`);
  setState({ program: { ...current, code: payload.code } });
}

export async function clean(): Promise<void> {
  if (!(await ensureSaved())) return;
  const removed = await operation('clean', t('Nettoyer', 'Clean'), '', () => call<string[]>('clean'), false);
  if (removed) toast(removed.length ? count(removed.length, ['élément supprimé', 'éléments supprimés'], ['item removed', 'items removed']) : t('Rien à nettoyer', 'Nothing to clean'), 'success');
}

export async function reveal(): Promise<void> {
  await call('reveal');
}

// Les dépendances

export async function refreshCache(): Promise<void> {
  try {
    setState({ cache: await call<Dependency[]>('cache') });
  } catch (error) {
    fail(error, t('Cache illisible', 'Unreadable cache'));
  }
}

export async function restore(): Promise<void> {
  if (!(await ensureSaved())) return;
  const report = await operation('restore', t('Restaurer', 'Restore'), '', () => call<RestoreReport>('restore'));
  if (!report) return;
  refreshCache();
  const missing = report.failed.length + report.warnings.length;
  if (missing) toast(count(missing, ['entrée à fournir', 'entrées à fournir'], ['entry to provide', 'entries to provide']), 'danger', [...report.failed, ...report.warnings].join('\n'));
  else if (report.rebuilt.length) toast(count(report.rebuilt.length, ['entrée reconstruite', 'entrées reconstruites'], ['entry rebuilt', 'entries rebuilt']), 'success');
  else toast(t('Le cache a tout', 'The cache has everything'), 'success');
}

// Ce qu'installer : la source, le tag ou le commit d'une branche, et le nom et la version des entrées.
export interface InstallChoice {
  name: string;
  version: string;
  source: string;
  tag: string | null;
  commit: string | null;
}

// Une entrée par runtime des configurations du projet, pour les plateformes de sa solution. Aucune
// entrée : la feuille des paramètres a été refermée.
export async function install(choice: InstallChoice): Promise<Dependency[] | undefined> {
  const entries = await operation('install', t('Installer', 'Install'), `${choice.name}@${choice.version}`, () =>
    call<Dependency[]>('install', choice.name, choice.version, choice.source, choice.tag, choice.commit)
  );
  if (!entries?.length) return undefined;
  await refreshCache();
  toast(t(`${choice.name} ${choice.version} installée`, `${choice.name} ${choice.version} installed`), 'success', entries.map(entry => entry.name).join(' · '));
  return entries;
}

// Lier un paquet à chaque configuration d'un target, ou à une seule.
export async function linkPackage(targetName: string, pkg: Package, only?: string): Promise<boolean> {
  const state = getState();
  const target = state.view?.project?.targets[targetName];
  if (!target) return false;
  const { calls, missing } = linkCalls(target, pkg, state.cache, only);
  if (missing.length) toast(t(`${pkg.name} n’a pas d’entrée pour ${missing.join(', ')}`, `${pkg.name} has no entry for ${missing.join(', ')}`), 'danger');
  return batch(calls);
}

export async function unlinkPackage(targetName: string, linked: Linked, only?: string): Promise<boolean> {
  const target = getState().view?.project?.targets[targetName];
  return target ? batch(unlinkCalls(target, linked, only)) : false;
}

// Changer le runtime d'une configuration change aussi l'entrée de chaque paquet qu'elle lie.
export async function changeRuntime(targetName: string, index: number, runtime: string): Promise<void> {
  if (!(await setField(['targets', targetName, 'configurations', index, 'runtime_library'], runtime))) return;
  const state = getState();
  const target = state.view?.project?.targets[targetName];
  if (!target) return;
  const { calls, missing } = relinkCalls(target, target.configurations[index], state.cache);
  if (missing.length) toast(t(`Pas d’entrée ${runtime} pour ${missing.join(', ')}`, `No ${runtime} entry for ${missing.join(', ')}`), 'danger');
  await batch(calls);
}

// Construire les plateformes de la solution qui manquent aux entrées d'un paquet.
export async function addPlatforms(entries: Dependency[], platforms: string[]): Promise<void> {
  for (const entry of entries) {
    const missing = platforms.filter(p => !entry.build.platforms.includes(p));
    if (!missing.length || entry.nature === 'header_only') continue;
    const done = await operation('install', t('Installer', 'Install'), `${entry.name}@${entry.version} · ${missing.join(' ')}`, () =>
      call<Dependency>('add_platforms', entry.name, entry.version, missing)
    );
    if (!done) break;
  }
  await refreshCache();
}

export async function vendorPackage(refs: DependencyRef[]): Promise<void> {
  await batch(refs.map(ref => ['vendor_dependency', [ref.name, ref.version]]));
}

// Le projet reprend les entrées du cache : l'enregistrement retire leur dossier de .cstarter/vendor/.
export async function unvendorPackage(refs: DependencyRef[]): Promise<void> {
  await batch(refs.map(ref => ['unvendor_dependency', [ref.name, ref.version]]));
}

export async function removeEntries(entries: Dependency[]): Promise<void> {
  try {
    for (const entry of entries) await call('remove_dependency', entry.name, entry.version);
    toast(t('Supprimée du cache', 'Removed from the cache'), 'success', entries.map(entry => entry.name).join(' · '));
  } catch (error) {
    fail(error, t('Suppression refusée', 'Removal refused'));
  }
  refreshCache();
}

export async function exportTarget(target: string, configuration: string, name: string, version: string): Promise<void> {
  if (!(await ensureSaved())) return;
  const dependency = await operation('build', t('Exporter', 'Export'), `${target} → ${name}@${version}`, c =>
    call<Dependency>('export_dependency', target, configuration, name, version, c)
  );
  if (dependency) {
    refreshCache();
    toast(t(`${dependency.name}@${dependency.version} dans le cache`, `${dependency.name}@${dependency.version} in the cache`), 'success');
  }
}

// git

export async function refreshGit(): Promise<void> {
  try {
    setState({ git: await call<GitStatus | null>('git_status') });
  } catch {
    setState({ git: null });
  }
}

export async function gitInit(lfs: boolean): Promise<void> {
  const written = await operation('git', 'git init', '', c => call<string[]>('git_init', lfs, c), false);
  if (written) toast(t('Dépôt prêt', 'Repository ready'), 'success', written.join(', '));
  refreshGit();
}

export async function gitCommit(message: string, paths: string[]): Promise<boolean> {
  const done = await operation('git', 'git commit', '', () => call('git_commit', message, paths).then(() => true), false);
  refreshGit();
  if (done) toast(t('Validé', 'Committed'), 'success', message.split('\n')[0]);
  return Boolean(done);
}

export async function gitPush(): Promise<void> {
  const done = await operation('git', 'git push', '', () => call('git_push').then(() => true));
  refreshGit();
  if (done) toast(t('Envoyé', 'Pushed'), 'success');
}

export async function gitRemotes(): Promise<Remote[]> {
  try {
    return await call<Remote[]>('git_remotes');
  } catch (error) {
    fail(error, t('Remotes illisibles', 'Unreadable remotes'));
    return [];
  }
}

export async function gitSetRemote(name: string, url: string): Promise<boolean> {
  try {
    await call<Remote[]>('git_set_remote', name, url);
    toast(t('Remote enregistré', 'Remote saved'), 'success', `${name} · ${url}`);
    return true;
  } catch (error) {
    fail(error, t('Remote refusé', 'Remote refused'));
    return false;
  }
}

export async function gitLog(): Promise<Commit[]> {
  try {
    return await call<Commit[]>('git_log', 30);
  } catch (error) {
    fail(error, t('Historique illisible', 'Unreadable history'));
    return [];
  }
}

export async function gitDiff(path: string): Promise<string | null> {
  try {
    return await call<string>('git_diff', path);
  } catch (error) {
    fail(error, t('Modifications illisibles', 'Unreadable changes'));
    return null;
  }
}

async function afterGit(result: { report: GitReport; view: View } | undefined, success: string): Promise<void> {
  if (!result) return refreshGit();
  showView(result.view, undefined, true);
  await refreshGit();
  const report = result.report;
  if (report.conflicts.length) {
    setState({ page: 'git' });
    toast(count(report.conflicts.length, ['fichier en conflit', 'fichiers en conflit'], ['file in conflict', 'files in conflict']), 'danger');
  } else if (report.problem) {
    toast(t('Solution non régénérée', 'Solution not regenerated'), 'danger', report.problem);
  } else {
    toast(success, 'success', report.written.length ? t('Solution régénérée', 'Solution regenerated') + ` · ${count(report.written.length, ['fichier', 'fichiers'], ['file', 'files'])}` : undefined);
  }
}

// pull, switch, merge et discard relisent .cstarter/ : les modifications en mémoire se règlent d'abord.
export async function gitPull(): Promise<void> {
  if (!(await settleUnsaved())) return;
  const result = await operation('git', 'git pull', '', c => call<{ report: GitReport; view: View }>('git_pull', c));
  await afterGit(result, t('À jour', 'Up to date'));
}

export async function gitSwitch(name: string, create = false): Promise<void> {
  if (!(await settleUnsaved())) return;
  const result = await operation('git', 'git switch', name, c => call<{ report: GitReport; view: View }>('git_switch', name, create, c), false);
  await afterGit(result, t(`Sur ${name}`, `On ${name}`));
}

export async function gitMerge(name: string): Promise<void> {
  if (!(await settleUnsaved())) return;
  const result = await operation('git', 'git merge', name, c => call<{ report: GitReport; view: View }>('git_merge', name, c));
  await afterGit(result, t(`${name} fusionnée`, `${name} merged`));
}

// Annuler les modifications d'un fichier : l'utilisateur l'a confirmé par la mèche.
export async function gitDiscard(paths: string[]): Promise<boolean> {
  if (!(await settleUnsaved())) return false;
  const result = await operation('git', 'git restore', paths.join(' '), c => call<{ report: GitReport; view: View }>('git_discard', paths, c), false);
  await afterGit(result, t('Modifications annulées', 'Changes discarded'));
  return Boolean(result);
}

export async function gitBranches(): Promise<string[]> {
  try {
    return await call<string[]>('git_branches');
  } catch (error) {
    fail(error, t('Branches illisibles', 'Unreadable branches'));
    return [];
  }
}

export async function editConflict(path: string): Promise<void> {
  try {
    await call('edit_conflict', path);
  } catch (error) {
    fail(error, t('Ouverture impossible', 'Cannot open'));
  }
}

// Un fichier réparé est préparé. Un .cstarter/ resté illisible pendant le conflit se relit alors.
export async function resolveConflict(path: string): Promise<void> {
  try {
    await call('git_resolve', path);
  } catch (error) {
    fail(error, t('Résolution refusée', 'Resolution refused'));
  }
  if (getState().view?.problem) await reload();
  else await refreshGit();
}

export async function reload(): Promise<void> {
  try {
    showView(await call<View>('reload'), undefined, true);
    refreshGit();
  } catch (error) {
    fail(error, t('Relecture impossible', 'Cannot reload'));
  }
}

// La distribution : une version plus récente se prépare en arrière-plan,
// et les prérequis manquants se montrent au premier lancement.

const PREREQUISITES_SHOWN = 'cstarter.prerequis';

async function prepareUpdate(): Promise<void> {
  try {
    setState({ update: await call<string | null>('update_prepare') });
  } catch {
    // update_prepare écrit déjà ses échecs dans l'onglet Sortie
  }
}

// Sur demande : la version prête s'annonce dans la barre de titre, sinon CStarter est à jour.
export async function checkForUpdate(): Promise<void> {
  try {
    const version = await call<string | null>('update_check');
    setState({ update: version });
    if (version) toast(t(`CStarter ${version} est prêt`, `CStarter ${version} is ready`), 'success', t('Mettre à jour, dans la barre de titre', 'Update, in the title bar'));
    else toast(t('CStarter est à jour', 'CStarter is up to date'), 'success', getState().version);
  } catch (error) {
    fail(error, t('Mise à jour indisponible', 'Update unavailable'));
  }
}

export async function installUpdate(): Promise<void> {
  if (!(await settleUnsaved())) return;
  try {
    await call('update_install');
  } catch (error) {
    fail(error, t('Mise à jour impossible', 'Update failed'));
  }
}

async function checkPrerequisites(): Promise<void> {
  try {
    setState({ prerequisites: await call<Prerequisite[]>('prerequisites') });
  } catch {
    return;
  }
  if (getState().prerequisites?.every(tool => tool.present)) return;
  let shown = true;
  try {
    shown = localStorage.getItem(PREREQUISITES_SHOWN) !== null;
    localStorage.setItem(PREREQUISITES_SHOWN, '1');
  } catch {
    // sans stockage, la liste reste à portée depuis l'accueil
  }
  if (!shown) showPrerequisites();
}

export function showPrerequisites(): void {
  openPrerequisites(installPrerequisite);
}

async function installPrerequisite(name: string): Promise<boolean> {
  const list = await operation('install', 'winget', name, () => call<Prerequisite[]>('install_prerequisite', name), false);
  if (!list) return false;
  setState({ prerequisites: list });
  if (list.find(tool => tool.name === name)?.present) toast(t(`${name} installé`, `${name} installed`), 'success');
  else toast(t(`${name} introuvable`, `${name} not found`), 'danger', t('Relancez CStarter', 'Restart CStarter'));
  return true;
}

export { fail };
