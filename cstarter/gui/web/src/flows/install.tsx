// Installer une bibliothèque : un lien, ou un dossier de la machine, puis la
// version d'un dépôt dans un menu, ou le nom et la version devinés de la source. Le téléchargement,
// l'analyse et ses paramètres suivent (lib/dialogs.tsx), puis une entrée par runtime du projet.
// Depuis un target, le paquet lui est aussitôt lié ; sinon, au seul target du projet, ou à ceux que
// l'on coche ; depuis l'accueil, à aucun.

import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { AlertCircleIcon, ArrowDown01Icon, Folder01Icon, GitBranchIcon, GithubIcon, GitlabIcon, Link01Icon, PackageIcon, Tag01Icon } from '@hugeicons/core-free-icons';
import type { IconSvgElement } from '@hugeicons/react';
import { install, linkPackage, pickFolder, toast, type InstallChoice } from '../lib/actions';
import { call } from '../lib/bridge';
import { t } from '../lib/i18n';
import { openSheet, SheetFrame } from '../lib/dialogs';
import type { Versions } from '../lib/model';
import type { Package } from '../lib/packages';
import { getState } from '../lib/store';
import { Menu, Popover, type MenuItem } from '../components/Popover';
import { typeIcon } from '../components/Sidebar';
import { Button, Icon, Input, Reveal, Toggle } from '../components/ui';
import './install.css';

export async function installFlow(target?: string): Promise<void> {
  const choice = await openSheet<InstallChoice>(close => <InstallSheet close={close} />, 580);
  if (!choice) return;
  const entries = await install(choice);
  if (!entries?.length) return;
  const pkg: Package = { key: `${choice.name}@${choice.version}`, name: choice.name, version: choice.version, entries };
  const targets = Object.keys(getState().view?.project?.targets ?? {});
  const chosen = target ? [target] : targets.length === 1 ? targets : targets.length ? ((await openSheet<string[]>(close => <LinkSheet pkg={pkg} close={close} />, 460)) ?? []) : [];
  for (const name of chosen) await linkPackage(name, pkg);
  if (chosen.length) toast(t(`${pkg.name} liée à ${chosen.join(', ')}`, `${pkg.name} linked to ${chosen.join(', ')}`), 'success');
}

// Un lien de GitHub ou de GitLab copié du navigateur, vers une branche ou un fichier, désigne le dépôt ;
// une archive reste une archive.
function normalize(link: string): string {
  const text = link.trim().replace(/^(?:https?:\/\/)?(?:www\.)?((?:github|gitlab)\.com\/)/i, 'https://$1');
  if (/\/(?:archive|releases\/download)\//i.test(text)) return text;
  const github = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+/i.exec(text);
  if (github) return github[0].replace(/\.git$/i, '');
  const gitlab = /^https:\/\/gitlab\.com\/[^?#\s]+/i.exec(text);
  if (gitlab) return gitlab[0].split('/-/')[0].replace(/\/+$/, '').replace(/\.git$/i, '');
  return text;
}

function kindOf(source: string): string {
  if (/\/(?:archive|releases\/download)\//i.test(source)) return 'url';
  if (/^https:\/\/github\.com\//i.test(source)) return 'github';
  if (/^https:\/\/gitlab\.com\//i.test(source)) return 'gitlab';
  if (source.startsWith('vcpkg:')) return 'vcpkg';
  if (source.startsWith('conan:')) return 'conan';
  return source.includes('://') ? 'url' : 'local';
}

const SOURCE_ICONS: Record<string, IconSvgElement> = {
  github: GithubIcon,
  gitlab: GitlabIcon,
  vcpkg: PackageIcon,
  conan: PackageIcon,
  url: Link01Icon,
  local: Folder01Icon
};

// Les débuts de lien que les pastilles écrivent dans le champ.
const PREFIXES: { label: string; prefix: string; icon: IconSvgElement }[] = [
  { label: 'GitHub', prefix: 'https://github.com/', icon: GithubIcon },
  { label: 'GitLab', prefix: 'https://gitlab.com/', icon: GitlabIcon },
  { label: 'vcpkg', prefix: 'vcpkg:', icon: PackageIcon },
  { label: 'conan', prefix: 'conan:', icon: PackageIcon }
];

// Un nom valide pour le cache, comme config.safe_name.
const safe = (text: string) => text.replace(/[^A-Za-z0-9_.-]/g, '_').replace(/^[.-]+|[.-]+$/g, '');
const unprefixed = (tag: string) => safe(tag.replace(/^v(?=\d)/i, ''));

// Ce qu'on installe d'un dépôt : un tag, ou une branche là où elle en est.
type Branch = Versions['branches'][number];
type Pick = { tag: string } | { branch: Branch };

interface Found {
  source: string;
  versions: Versions;
}

function InstallSheet({ close }: { close: (value?: InstallChoice) => void }) {
  const [link, setLink] = useState('');
  const [found, setFound] = useState<Found | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [looking, setLooking] = useState(false);
  const [pick, setPick] = useState<Pick | null>(null);
  const [name, setName] = useState('');
  const [version, setVersion] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const request = useRef(0);
  const source = normalize(link);
  const current = found?.source === source ? found : null;
  const repository = current && (current.versions.source === 'github' || current.versions.source === 'gitlab');

  // Ce que la source propose s'affiche seul : aussitôt un lien collé ou un dossier choisi, et après une
  // pause dans la frappe. L'API de GitHub limite les appels sans jeton : chaque lettre n'en coûte pas.
  const lookup = useCallback(async (location: string) => {
    const id = ++request.current;
    setLooking(true);
    setFailed(null);
    try {
      const versions = await call<Versions>('versions', location);
      if (id !== request.current) return;
      setFound({ source: location, versions });
      const guess = guessEntry(location, versions);
      setName(guess.name);
      setVersion(guess.version);
      const latest = versions.latest ?? versions.tags[0];
      setPick(latest ? { tag: latest } : versions.branches[0] ? { branch: versions.branches[0] } : null);
    } catch (error) {
      if (id === request.current) setFailed(error instanceof Error ? error.message : String(error));
    } finally {
      if (id === request.current) setLooking(false);
    }
  }, []);
  const pasted = useRef(false);
  useEffect(() => {
    request.current++;
    setLooking(false);
    setFailed(null);
    if (!source || source.endsWith('/') || source.endsWith(':')) return;
    const timer = setTimeout(() => lookup(source), pasted.current ? 0 : 900);
    pasted.current = false;
    return () => clearTimeout(timer);
  }, [source]);

  const repositoryName = source.replace(/^https:\/\/[^/]+\//, '').split('/').pop() ?? '';
  const choice: InstallChoice | null = !current
    ? null
    : repository
      ? pick
        ? 'tag' in pick
          ? { name: safe(repositoryName), version: unprefixed(pick.tag), source, tag: pick.tag, commit: null }
          : { name: safe(repositoryName), version: `${safe(pick.branch.name)}-${pick.branch.commit.slice(0, 7)}`, source, tag: null, commit: pick.branch.commit }
        : null
      : safe(name.trim()) && safe(version.trim())
        ? { name: safe(name.trim()), version: safe(version.trim()), source, tag: current.versions.source === 'vcpkg' ? safe(version.trim()) : null, commit: null }
        : null;

  const browse = async () => {
    const folder = await pickFolder();
    if (!folder) return;
    pasted.current = true;
    setLink(folder);
  };
  const prefill = (prefix: string) => {
    setLink(prefix);
    requestAnimationFrame(() => {
      input.current?.focus();
      input.current?.setSelectionRange(prefix.length, prefix.length);
    });
  };
  const submit = () => choice && close(choice);

  return (
    <SheetFrame
      title={t('Installer une bibliothèque', 'Install a library')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close()}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={submit} disabled={!choice || looking}>
            {t('Installer', 'Install')}
          </Button>
        </>
      }
    >
      <div className={`source${failed ? ' source--failed' : ''}`}>
        <span className="source__icon">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={looking ? 'looking' : failed ? 'failed' : source ? kindOf(source) : 'empty'}
              className="source__glyph"
              initial={{ opacity: 0, scale: 0.5, filter: 'blur(4px)' }}
              animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, scale: 0.5, filter: 'blur(4px)' }}
              transition={{ type: 'spring', bounce: 0.25, duration: 0.35 }}
            >
              {looking ? <span className="source__spinner" /> : <Icon icon={failed ? AlertCircleIcon : source ? SOURCE_ICONS[kindOf(source)] : Link01Icon} size={17} />}
            </motion.span>
          </AnimatePresence>
        </span>
        <input
          ref={input}
          className="source__input"
          value={link}
          placeholder="https://github.com/…"
          autoFocus
          spellCheck={false}
          onChange={event => setLink(event.target.value)}
          onPaste={() => (pasted.current = true)}
          onKeyDown={event => {
            if (event.key !== 'Enter') return;
            if (choice) submit();
            else if (source && !looking) lookup(source);
          }}
        />
        <Button tone="ghost" size="sm" icon={Folder01Icon} title={t('Choisir un dossier', 'Choose a folder')} onClick={browse} />
      </div>
      <Reveal when={Boolean(failed)}>
        <div className="source__error">{failed}</div>
      </Reveal>
      <Reveal when={!source}>
        <div className="source__kinds">
          {PREFIXES.map(kind => (
            <button key={kind.label} type="button" className="source__kind" onClick={() => prefill(kind.prefix)}>
              <Icon icon={kind.icon} size={13} />
              {kind.label}
            </button>
          ))}
        </div>
      </Reveal>
      <Reveal when={Boolean(current)}>
        {repository && current ? (
          <div className="sheet__field install__version">
            <label>Version</label>
            <VersionSelect versions={current.versions} value={pick} onChange={setPick} />
          </div>
        ) : (
          <div className="sheet__grid install__version">
            <div className="sheet__field">
              <label>{t('Nom', 'Name')}</label>
              <Input value={name} onChange={setName} mono onEnter={submit} />
            </div>
            <div className="sheet__field">
              <label>Version</label>
              <Input value={version} onChange={setVersion} mono onEnter={submit} />
            </div>
          </div>
        )}
      </Reveal>
    </SheetFrame>
  );
}

// La version d'un dépôt : ses tags, la plus récente d'abord, puis ses branches.
function VersionSelect({ versions, value, onChange }: { versions: Versions; value: Pick | null; onChange: (pick: Pick) => void }) {
  const anchor = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const items: MenuItem[] = [
    ...versions.tags.map(tag => ({ value: `tag:${tag}`, label: tag, mono: true, icon: Tag01Icon, tag: tag === versions.latest ? t('dernière', 'latest') : undefined, group: 'Versions' })),
    ...versions.branches.map(branch => ({ value: `branch:${branch.name}`, label: branch.name, mono: true, icon: GitBranchIcon, tag: branch.commit.slice(0, 7), group: t('Branches', 'Branches') }))
  ];
  const label = !value ? '' : 'tag' in value ? value.tag : value.branch.name;
  return (
    <>
      <button ref={anchor} type="button" className="version-select" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon icon={value && 'branch' in value ? GitBranchIcon : Tag01Icon} size={15} className="version-select__icon" />
        <span className="version-select__label mono">{label}</span>
        {value && 'tag' in value && value.tag === versions.latest ? <span className="version-select__latest">{t('dernière', 'latest')}</span> : null}
        {value && 'branch' in value ? <span className="version-select__commit mono">{value.branch.commit.slice(0, 7)}</span> : null}
        <Icon icon={ArrowDown01Icon} size={14} className="version-select__chevron" />
      </button>
      <Popover anchor={anchor} open={open} onClose={close} width={anchor.current?.offsetWidth ?? 420}>
        <Menu
          items={items}
          filter={items.length > 8}
          placeholder={t('Rechercher', 'Search')}
          onSelect={selected => {
            setOpen(false);
            const [kind, rest] = [selected.slice(0, selected.indexOf(':')), selected.slice(selected.indexOf(':') + 1)];
            if (kind === 'tag') onChange({ tag: rest });
            else {
              const branch = versions.branches.find(b => b.name === rest);
              if (branch) onChange({ branch });
            }
          }}
        />
      </Popover>
    </>
  );
}

// Le nom et la version de l'entrée, devinés de la source. Une archive de GitHub dit son dépôt et son
// tag : imgui et 1.92.9b.
function guessEntry(source: string, versions: Versions): { name: string; version: string } {
  if (versions.source === 'vcpkg') return { name: safe(source.slice(6)), version: versions.latest ?? '' };
  if (versions.source === 'conan') {
    const [name, rest = ''] = source.slice(6).split('/');
    return { name: safe(name), version: safe(rest.split(/[@#]/)[0]) };
  }
  const url = versions.source === 'url';
  const hosted =
    /^https:\/\/github\.com\/[^/]+\/([^/]+)\/archive\/(?:refs\/(?:tags|heads)\/)?(.+?)\.(?:zip|tar\.gz|tgz)$/i.exec(source) ??
    /^https:\/\/github\.com\/[^/]+\/([^/]+)\/releases\/download\/([^/]+)\//i.exec(source);
  if (url && hosted) return { name: safe(hosted[1]), version: unprefixed(hosted[2]) };
  // Une autre archive, ou un dossier : le nom de fichier, sans son extension, porte souvent la version.
  const last = source.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? '';
  const file = url ? last.replace(/[?#].*$/, '').replace(/\.(?:zip|tgz|tar(?:\.(?:gz|xz|bz2))?)$/i, '') : last;
  const found = /\d+(?:\.\d+)+/.exec(file)?.[0];
  const today = new Date().toISOString().slice(0, 10).replaceAll('-', '.');
  return {
    name: safe(file.replace(/[-_.]*v?\d+(?:\.\d+)+.*$/i, '')) || safe(file) || (url ? 'archive' : 'local'),
    version: found ?? (url ? today : 'local')
  };
}

// Installée hors d'un target : les targets à qui la lier, le target de démarrage coché d'avance.
function LinkSheet({ pkg, close }: { pkg: Package; close: (value?: string[]) => void }) {
  const project = getState().view?.project;
  const targets = project ? Object.values(project.targets) : [];
  const [chosen, setChosen] = useState<Set<string>>(() => new Set(project?.solution.startup_target ? [project.solution.startup_target] : []));
  const toggle = (name: string, on: boolean) => {
    const next = new Set(chosen);
    if (on) next.add(name);
    else next.delete(name);
    setChosen(next);
  };
  return (
    <SheetFrame
      title={
        <>
          {t('Lier', 'Link')} <span className="link-sheet__name">{pkg.name}</span>
        </>
      }
      actions={
        <>
          <Button tone="ghost" onClick={() => close([])}>
            {t('Plus tard', 'Later')}
          </Button>
          <Button tone="primary" onClick={() => close([...chosen])} disabled={!chosen.size}>
            {t('Lier', 'Link')}
          </Button>
        </>
      }
    >
      <div className="link-sheet">
        {targets.map(target => (
          <label key={target.name} className="link-sheet__row">
            <Icon icon={typeIcon(target.type)} size={15} className="link-sheet__icon" />
            <span className="link-sheet__target">{target.name}</span>
            <Toggle on={chosen.has(target.name)} onChange={on => toggle(target.name, on)} label={target.name} />
          </label>
        ))}
      </div>
    </SheetFrame>
  );
}
