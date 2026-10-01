// git : la branche en titre, dont le menu bascule, fusionne ou en crée une ; son
// remote, qu'Envoyer demande s'il manque ; les conflits d'abord, puis les fichiers à cocher pour le
// prochain commit, dont un clic montre les modifications ; enfin l'historique. Pendant une fusion,
// git valide tout l'index : tout reste coché.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  AlertCircleIcon,
  ArrowDown01Icon,
  CloudDownloadIcon,
  CloudUploadIcon,
  Delete02Icon,
  FileEditIcon,
  GitBranchIcon,
  GitMergeIcon,
  Link01Icon,
  PlusSignIcon,
  RefreshIcon,
  Tick02Icon
} from '@hugeicons/core-free-icons';
import FuseButton from '../reactbits/FuseButton';
import {
  editConflict,
  gitBranches,
  gitCommit,
  gitDiff,
  gitDiscard,
  gitInit,
  gitLog,
  gitMerge,
  gitPull,
  gitPush,
  gitRemotes,
  gitSetRemote,
  gitSwitch,
  refreshGit,
  reload,
  resolveConflict
} from '../lib/actions';
import { openSheet, SheetFrame } from '../lib/dialogs';
import { count, language, t } from '../lib/i18n';
import { gitStates } from '../lib/labels';
import type { Commit, GitChange, GitStatus, Remote } from '../lib/model';
import { useStore } from '../lib/store';
import { Popover } from '../components/Popover';
import { Button, Chip, Empty, Icon, Input, PageHeader, Section, Toggle } from '../components/ui';
import './Git.css';
import './pages.css';

export default function Git() {
  const git = useStore(s => s.git);
  useEffect(() => {
    refreshGit();
  }, []);
  if (git === undefined) return null;
  if (git === null) return <NoRepository />;
  return <Changes git={git} />;
}

function NoRepository() {
  const [lfs, setLfs] = useState(false);
  return (
    <>
      <PageHeader title="Git" />
      <Empty icon={GitBranchIcon} title={t('Aucun dépôt git', 'No git repository')}>
        <div className="git-init">
          <label className="git-init__lfs">
            <Toggle on={lfs} onChange={setLfs} label="Git LFS" />
            {t('Binaires vendorés dans Git LFS', 'Vendored binaries in Git LFS')}
          </label>
          <Button tone="primary" onClick={() => gitInit(lfs)}>
            {t('Initialiser le dépôt', 'Initialize the repository')}
          </Button>
        </div>
      </Empty>
    </>
  );
}

// Un fichier dont les modifications s'annulent : le dernier commit l'a, et il n'est ni en conflit
// ni renommé (bridge.py refuse les autres, CStarter ne supprime pas un fichier de l'utilisateur).
const discardable = (change: GitChange) => !change.conflicted && !change.original && change.index !== '?' && change.index !== 'A';

function Changes({ git }: { git: GitStatus }) {
  const problem = useStore(s => s.view?.problem);
  const busy = useStore(s => s.busy);
  const conflicts = git.changes.filter(c => c.conflicted);
  const changes = git.changes.filter(c => !c.conflicted);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState('');
  const [remotes, setRemotes] = useState<Remote[] | null>(null);
  const [history, setHistory] = useState<Commit[]>([]);
  const checked = useMemo(() => changes.filter(c => git.merging || !excluded.has(c.path)).map(c => c.path), [changes, excluded, git.merging]);

  // L'état du dépôt change après chaque commit, envoi ou fusion : son remote et son historique suivent.
  useEffect(() => {
    gitRemotes().then(setRemotes);
    gitLog().then(setHistory);
  }, [git]);

  const toggle = (path: string) => {
    const next = new Set(excluded);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setExcluded(next);
  };
  const toggleAll = () => setExcluded(checked.length === changes.length ? new Set(changes.map(c => c.path)) : new Set());
  const commit = async () => {
    if (await gitCommit(message.trim(), checked)) {
      setMessage('');
      setExcluded(new Set());
    }
  };
  // Envoyer sans remote : il se demande d'abord.
  const push = async () => {
    if (remotes && !remotes.length && !(await remoteSheet(null))) return;
    await gitPush();
  };
  const origin = remotes?.find(remote => remote.name === 'origin') ?? remotes?.[0];

  return (
    <>
      <PageHeader
        title={<BranchMenu git={git} />}
        meta={
          <>
            {origin ? (
              <button type="button" className="git-remote" title={t('Changer l’adresse du remote', 'Change the remote address')} onClick={() => remoteSheet(origin).then(() => refreshGit())}>
                <Icon icon={Link01Icon} size={12} stroke={2} />
                <span className="git-remote__name">{origin.name}</span>
                <span className="git-remote__url mono">{origin.url.replace(/^https?:\/\//, '')}</span>
              </button>
            ) : remotes ? (
              <button type="button" className="git-remote git-remote--none" onClick={() => remoteSheet(null).then(() => refreshGit())}>
                <Icon icon={PlusSignIcon} size={12} stroke={2} />
                {t('Ajouter un remote', 'Add a remote')}
              </button>
            ) : null}
            {git.upstream ? <Chip>{git.upstream}</Chip> : null}
            {git.ahead ? <Chip tone="success">↑ {git.ahead}</Chip> : null}
            {git.behind ? <Chip tone="warning">↓ {git.behind}</Chip> : null}
            {git.merging ? <Chip tone="warning">{t('Fusion en cours', 'Merge in progress')}</Chip> : null}
          </>
        }
        actions={
          <>
            <Button icon={CloudDownloadIcon} onClick={gitPull} disabled={busy || !remotes?.length}>
              {t('Récupérer', 'Pull')}
            </Button>
            <Button icon={CloudUploadIcon} onClick={push} disabled={busy || !git.branch}>
              {t('Envoyer', 'Push')}
            </Button>
          </>
        }
      />

      {problem ? (
        <div className="banner">
          <Icon icon={AlertCircleIcon} size={18} className="banner__icon" />
          <span className="banner__text mono">{problem}</span>
          <Button tone="secondary" size="sm" icon={RefreshIcon} onClick={reload}>
            {t('Relire', 'Reload')}
          </Button>
        </div>
      ) : null}

      {conflicts.length ? (
        <Section title={t('En conflit', 'In conflict')}>
          {conflicts.map(change => (
            <div key={change.path} className="git-row git-row--conflict">
              <span className="git-state git-state--U">!</span>
              <Path change={change} />
              <span className="git-row__actions">
                <Button tone="ghost" size="sm" icon={FileEditIcon} onClick={() => editConflict(change.path)}>
                  {t('Ouvrir', 'Open')}
                </Button>
                <Button tone="secondary" size="sm" icon={Tick02Icon} onClick={() => resolveConflict(change.path)} disabled={busy}>
                  {t('Marquer résolu', 'Mark resolved')}
                </Button>
              </span>
            </div>
          ))}
        </Section>
      ) : null}

      <Section
        title={
          <span className="git-head">
            {changes.length ? <Check on={checked.length === changes.length} partial={checked.length > 0 && checked.length < changes.length} onClick={toggleAll} disabled={git.merging} /> : null}
            {changes.length ? count(changes.length, ['fichier', 'fichiers'], ['file', 'files']) : t('Rien à valider', 'Nothing to commit')}
          </span>
        }
      >
        <AnimatePresence initial={false}>
          {changes.map(change => (
            <motion.div
              key={change.path}
              layout
              className="git-row"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ type: 'spring', bounce: 0, duration: 0.3 }}
            >
              <Check on={checked.includes(change.path)} onClick={() => toggle(change.path)} disabled={git.merging} />
              <State change={change} />
              <button type="button" className="git-row__open" title={t('Voir les modifications', 'See the changes')} onClick={() => diffSheet(change)}>
                <Path change={change} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </Section>

      {changes.length || git.merging ? (
        <div className="composer">
          <textarea
            className="field composer__message"
            rows={3}
            value={message}
            placeholder={t('Message du commit', 'Commit message')}
            spellCheck={false}
            onChange={e => setMessage(e.target.value)}
          />
          <div className="composer__actions">
            <Button tone="primary" icon={Tick02Icon} onClick={commit} disabled={busy || !message.trim() || (!checked.length && !git.merging) || conflicts.length > 0}>
              {checked.length ? t('Valider', 'Commit') + ` ${count(checked.length, ['fichier', 'fichiers'], ['file', 'files'])}` : t('Valider', 'Commit')}
            </Button>
          </div>
        </div>
      ) : null}

      {history.length ? (
        <Section title={t('Historique', 'History')}>
          {history.map(entry => (
            <div key={entry.hash} className="commit-row">
              <span className="commit-row__hash mono">{entry.hash.slice(0, 7)}</span>
              <span className="commit-row__subject">{entry.subject}</span>
              <span className="commit-row__author">{entry.author}</span>
              <span className="commit-row__date">{when(entry.date)}</span>
            </div>
          ))}
        </Section>
      ) : null}
    </>
  );
}

// Une date de git, dans la langue de l'interface.
function when(date: string): string {
  const moment = new Date(date);
  return Number.isNaN(moment.getTime()) ? date : moment.toLocaleString(language() === 'en' ? 'en-GB' : 'fr-FR', { dateStyle: 'medium', timeStyle: 'short' });
}

// Le remote du dépôt : son nom et son adresse. Renvoie vrai s'il est enregistré.
async function remoteSheet(remote: Remote | null): Promise<boolean> {
  const chosen = await openSheet<Remote>(close => <RemoteSheet remote={remote} close={close} />, 520);
  return Boolean(chosen && (await gitSetRemote(chosen.name, chosen.url)));
}

function RemoteSheet({ remote, close }: { remote: Remote | null; close: (value?: Remote) => void }) {
  const [name, setName] = useState(remote?.name ?? 'origin');
  const [url, setUrl] = useState(remote?.url ?? '');
  const ready = Boolean(name.trim() && url.trim());
  const submit = () => ready && close({ name: name.trim(), url: url.trim() });
  return (
    <SheetFrame
      title={remote ? t('Adresse du remote', 'Remote address') : t('Ajouter un remote', 'Add a remote')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close()}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={submit} disabled={!ready}>
            {t('Enregistrer', 'Save')}
          </Button>
        </>
      }
    >
      <div className="sheet__form">
        <div className="sheet__grid sheet__grid--remote">
          <div className="sheet__field">
            <label>{t('Nom', 'Name')}</label>
            <Input value={name} onChange={setName} mono onEnter={submit} />
          </div>
          <div className="sheet__field">
            <label>{t('Adresse', 'Address')}</label>
            <Input value={url} onChange={setUrl} mono autoFocus placeholder="https://github.com/…" onEnter={submit} />
          </div>
        </div>
      </div>
    </SheetFrame>
  );
}

// Les modifications d'un fichier depuis le dernier commit, et, s'il le permet, leur annulation.
async function diffSheet(change: GitChange): Promise<void> {
  const text = await gitDiff(change.path);
  if (text === null) return;
  await openSheet<void>(close => <DiffSheet change={change} text={text} close={close} />, 960);
}

function DiffSheet({ change, text, close }: { change: GitChange; text: string; close: () => void }) {
  const lines = text.split('\n');
  const kind = (line: string) =>
    line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') || line.startsWith('index ') || line.startsWith('new file') || line.startsWith('deleted file') || line.startsWith('similarity') || line.startsWith('rename ')
      ? 'meta'
      : line.startsWith('@@')
        ? 'hunk'
        : line.startsWith('+')
          ? 'add'
          : line.startsWith('-')
            ? 'del'
            : 'same';
  return (
    <SheetFrame
      title={<span className="mono diff__title">{change.path}</span>}
      actions={
        <>
          {discardable(change) ? (
            <span className="sheet__left">
              <FuseButton
                label={t('Annuler les modifications', 'Discard the changes')}
                undoLabel={t('Garder', 'Keep')}
                doneLabel={t('Annulées', 'Discarded')}
                icon={<Icon icon={Delete02Icon} size={14} stroke={1.9} />}
                commitOn="fuseEnd"
                undoWindow={2600}
                size="sm"
                radius={9}
                background="rgba(255,107,107,0.12)"
                color="#ff8f8f"
                fuseColor="#ff6b6b"
                onCommit={async () => {
                  if (await gitDiscard([change.path])) close();
                }}
              />
            </span>
          ) : null}
          <Button tone="ghost" onClick={() => close()}>
            {t('Fermer', 'Close')}
          </Button>
        </>
      }
    >
      {text.trim() ? (
        <pre className="diff">
          {lines.map((line, i) => (
            <span key={i} className={`diff__line diff__line--${kind(line)}`}>
              {line || ' '}
            </span>
          ))}
        </pre>
      ) : (
        <div className="faint">{t('Aucune modification de contenu', 'No content change')}</div>
      )}
    </SheetFrame>
  );
}

// La branche courante, en titre : son menu liste les autres. Un clic bascule, l'icône de fusion la
// fusionne dans la courante, et le champ du bas en crée une et bascule dessus.
function BranchMenu({ git }: { git: GitStatus }) {
  const busy = useStore(s => s.busy);
  const anchor = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [branches, setBranches] = useState<string[]>([]);
  const [name, setName] = useState('');
  const close = useCallback(() => setOpen(false), []);
  useEffect(() => {
    if (open) gitBranches().then(setBranches);
    else setName('');
  }, [open]);
  const run = (action: () => Promise<void>) => {
    setOpen(false);
    action();
  };
  const current = git.branch;
  return (
    <>
      <button ref={anchor} className="branch-title" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon icon={GitBranchIcon} size={22} stroke={1.8} className="branch-title__icon" />
        <span>{current ?? t('HEAD détachée', 'Detached HEAD')}</span>
        <Icon icon={ArrowDown01Icon} size={16} stroke={2} className="branch-title__chevron" />
      </button>
      <Popover anchor={anchor} open={open} onClose={close} width={300}>
        <div className="branches">
          {branches.map(branch => (
            <div key={branch} className={`branches__row${branch === current ? ' branches__row--on' : ''}`}>
              <button className="branches__name" disabled={busy || branch === current} onClick={() => run(() => gitSwitch(branch))}>
                <Icon icon={branch === current ? Tick02Icon : GitBranchIcon} size={14} />
                <span>{branch}</span>
              </button>
              {branch !== current && current ? (
                <Button tone="ghost" size="sm" icon={GitMergeIcon} title={t(`Fusionner dans ${current}`, `Merge into ${current}`)} disabled={busy} onClick={() => run(() => gitMerge(branch))} />
              ) : null}
            </div>
          ))}
          <label className="branches__new">
            <Icon icon={PlusSignIcon} size={14} />
            <input
              value={name}
              placeholder={t('Nouvelle branche', 'New branch')}
              spellCheck={false}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && name.trim() && !busy) run(() => gitSwitch(name.trim(), true));
              }}
            />
          </label>
        </div>
      </Popover>
    </>
  );
}

function Check({ on, partial, onClick, disabled }: { on: boolean; partial?: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button className={`check${on ? ' check--on' : ''}${partial ? ' check--partial' : ''}`} role="checkbox" aria-checked={partial ? 'mixed' : on} onClick={onClick} disabled={disabled}>
      <AnimatePresence>
        {on || partial ? (
          <motion.span className="check__mark" initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.4, opacity: 0 }} transition={{ type: 'spring', bounce: 0.35, duration: 0.3 }}>
            {partial ? <span className="check__bar" /> : <Icon icon={Tick02Icon} size={11} stroke={3} />}
          </motion.span>
        ) : null}
      </AnimatePresence>
    </button>
  );
}

function State({ change }: { change: GitChange }) {
  const letter = change.index === '?' ? '?' : change.index !== '.' ? change.index : change.worktree;
  return (
    <span className={`git-state git-state--${letter === '?' ? 'new' : letter}`} title={gitStates()[letter] ?? letter}>
      {letter === '?' ? '+' : letter}
    </span>
  );
}

function Path({ change }: { change: GitChange }) {
  const slash = change.path.lastIndexOf('/');
  return (
    <span className="git-path">
      <span className="git-path__dir">{slash >= 0 ? change.path.slice(0, slash + 1) : ''}</span>
      <span className="git-path__name">{change.path.slice(slash + 1)}</span>
      {change.original ? <span className="git-path__from"> ← {change.original}</span> : null}
    </span>
  );
}
