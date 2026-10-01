// La barre de titre, dessinée par la page : Windows la fait glisser et ancre la fenêtre (Aero Snap)
// par bridge.py, dès que le pointeur a bougé de quelques pixels. Un double clic agrandit ou restaure.
// Le logo ouvre le menu de CStarter : sa langue, ses outils, ses mises à jour. Au centre, compiler et
// exécuter ; à droite, ouvrir la solution dans Visual Studio. Sans projet ouvert, à droite, le compte
// GitHub, ou de quoi se connecter.

import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowDown01Icon,
  GitBranchIcon,
  GithubIcon,
  HammerIcon,
  LanguageSquareIcon,
  Layers01Icon,
  PlayIcon,
  RefreshIcon,
  SquareArrowUpRightIcon,
  SystemUpdate01Icon,
  Tick02Icon,
  Wrench01Icon
} from '@hugeicons/core-free-icons';
import CallChip from '../reactbits/CallChip';
import GlideSelect from '../reactbits/GlideSelect';
import StatusMark from '../reactbits/StatusMark';
import {
  buildAll,
  buildSelected,
  checkForUpdate,
  chooseLanguage,
  generate,
  githubLogin,
  installUpdate,
  navigate,
  openInVisualStudio,
  requestClose,
  runSelected,
  selectPair,
  showPrerequisites
} from '../lib/actions';
import { call } from '../lib/bridge';
import { t } from '../lib/i18n';
import { statusWords } from '../lib/labels';
import { solutionConfigurations } from '../lib/model';
import { setState, useProject, useStore } from '../lib/store';
import { Menu, Popover, type MenuItem } from './Popover';
import { Button, Icon, Kbd } from './ui';
import Logo from './Logo';
import './TitleBar.css';

const INTERACTIVE = 'button, input, textarea, select, a, [role="combobox"], [role="listbox"], .no-drag';
// La durée attendue de chaque sorte d'opération, pour la jauge de sa pastille.
const EXPECTED: Record<string, number> = { build: 14000, generate: 900, install: 40000, restore: 20000, clone: 20000, import: 20000, read: 3000 };

export default function TitleBar() {
  const view = useStore(s => s.view);
  const maximized = useStore(s => s.maximized);
  // Sur l'accueil, le grand titre nomme déjà CStarter ; avant le démarrage, rien ne paraît pour s'effacer.
  const welcome = useStore(s => !s.booted || s.home === 'start');
  const project = view?.project;

  // Un simple clic ne lance pas la boucle de déplacement de Windows : elle garderait la souris, et
  // le double clic n'arriverait jamais à la page.
  const onMouseDown = (event: MouseEvent) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest(INTERACTIVE)) return;
    const x = event.screenX;
    const y = event.screenY;
    const move = (moved: globalThis.MouseEvent) => {
      if (Math.abs(moved.screenX - x) + Math.abs(moved.screenY - y) < 4) return;
      stop();
      call('window_press', 'caption');
    };
    const stop = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', stop);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', stop);
  };

  const onDoubleClick = (event: MouseEvent) => {
    if (!(event.target as HTMLElement).closest(INTERACTIVE)) call('window_toggle_maximize');
  };

  return (
    <header className="titlebar" onMouseDown={onMouseDown} onDoubleClick={onDoubleClick}>
      <div className="titlebar__left">
        <AppMenu />
        {view?.root ? (
          <>
            <span className="titlebar__project">{project?.name ?? view.root.split(/[\\/]/).pop()}</span>
            <AnimatePresence>
              {view.dirty ? (
                <motion.span
                  className="titlebar__dirty"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={{ type: 'spring', bounce: 0.4, duration: 0.4 }}
                />
              ) : null}
            </AnimatePresence>
            <BranchChip />
          </>
        ) : welcome ? null : (
          <span className="titlebar__project">CStarter</span>
        )}
      </div>
      <div className="titlebar__center">{project ? <BuildControls /> : null}</div>
      <div className="titlebar__right">
        <UpdateChip />
        <RunChip />
        {project ? (
          <Button tone="ghost" size="sm" icon={SquareArrowUpRightIcon} onClick={openInVisualStudio} className="titlebar__vs">
            Visual Studio
          </Button>
        ) : view && !view.root ? (
          <GithubAccount />
        ) : null}
        <WindowControls maximized={maximized} />
      </div>
    </header>
  );
}

// Le compte GitHub que Git Credential Manager connaît ; sans compte, de quoi se connecter. Rien
// tant qu'on ne le sait pas : le bouton ne paraît pas pour disparaître aussitôt.
function GithubAccount() {
  const account = useStore(s => s.github);
  const busy = useStore(s => s.busy);
  const look = {
    initial: { opacity: 0, scale: 0.92, filter: 'blur(6px)' },
    animate: { opacity: 1, scale: 1, filter: 'blur(0px)' },
    exit: { opacity: 0, scale: 0.96, filter: 'blur(4px)', transition: { duration: 0.14 } },
    transition: { type: 'spring' as const, bounce: 0, duration: 0.36 }
  };
  return (
    <AnimatePresence mode="popLayout" initial={false}>
      {account ? (
        <motion.span key="account" className="titlebar__github titlebar__github--known" title={t('Compte GitHub', 'GitHub account')} {...look}>
          <Icon icon={GithubIcon} size={14} stroke={1.8} />
          <span>{account}</span>
        </motion.span>
      ) : account === null ? (
        <motion.button key="signin" type="button" className="titlebar__github" onClick={githubLogin} disabled={busy} whileTap={{ scale: 0.96 }} {...look}>
          <Icon icon={GithubIcon} size={14} stroke={1.8} />
          <span>{t('Se connecter à GitHub', 'Sign in to GitHub')}</span>
        </motion.button>
      ) : null}
    </AnimatePresence>
  );
}

// Le menu de CStarter, derrière son logo : la langue, les outils qu'il lance, ses mises à jour.
function AppMenu() {
  const anchor = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const language = useStore(s => s.language);
  const version = useStore(s => s.version);
  const missing = useStore(s => s.prerequisites?.filter(tool => !tool.present).length ?? 0);
  const items: MenuItem[] = [
    { value: 'lang:fr', label: 'Français', icon: language === 'fr' ? Tick02Icon : LanguageSquareIcon, group: t('Langue', 'Language') },
    { value: 'lang:en', label: 'English', icon: language === 'en' ? Tick02Icon : LanguageSquareIcon, group: t('Langue', 'Language') },
    { value: 'tools', label: t('Outils', 'Tools'), icon: Wrench01Icon, tag: missing ? t(`${missing} à installer`, `${missing} to install`) : undefined, group: 'CStarter' },
    { value: 'update', label: t('Rechercher une mise à jour', 'Check for updates'), icon: SystemUpdate01Icon, tag: version, group: 'CStarter' }
  ];
  return (
    <>
      <button ref={anchor} type="button" className="titlebar__logo" aria-label="CStarter" title={t('Menu de CStarter', 'CStarter menu')} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Logo size={20} />
      </button>
      <Popover anchor={anchor} open={open} onClose={close} width={280}>
        <Menu
          items={items}
          onSelect={value => {
            setOpen(false);
            if (value.startsWith('lang:')) chooseLanguage(value.slice(5) as 'fr' | 'en');
            else if (value === 'tools') showPrerequisites();
            else checkForUpdate();
          }}
        />
      </Popover>
    </>
  );
}

function BranchChip() {
  const git = useStore(s => s.git);
  if (!git?.branch) return null;
  const changed = git.changes.length;
  return (
    <button className="titlebar__branch no-drag" onClick={() => navigate('git')}>
      <Icon icon={GitBranchIcon} size={13} stroke={2} />
      <span>{git.branch}</span>
      {changed ? <span className="titlebar__count">{changed}</span> : null}
    </button>
  );
}

function BuildControls() {
  const project = useProject();
  const pair = useStore(s => s.pair);
  const busy = useStore(s => s.busy);
  const more = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const configurations = solutionConfigurations(project);
  if (!pair || !configurations.length) return null;
  const startup = project.solution.startup_target;
  const runnable = Boolean(startup && project.targets[startup]?.type === 'executable');
  return (
    <div className="build no-drag">
      <GlideSelect
        value={pair.configuration}
        onChange={value => selectPair(value, pair.platform)}
        options={configurations}
        size="sm"
        radius={9}
        menuWidth={170}
        surfaceColor="rgba(255,255,255,0.055)"
        highlightColor="#2a2a31"
        ariaLabel="Configuration"
      />
      <GlideSelect
        value={pair.platform}
        onChange={value => selectPair(pair.configuration, value)}
        options={project.solution.platforms}
        size="sm"
        radius={9}
        menuWidth={130}
        surfaceColor="rgba(255,255,255,0.055)"
        highlightColor="#2a2a31"
        ariaLabel={t('Plateforme', 'Platform')}
      />
      <div className="split">
        <Button tone="primary" size="sm" icon={HammerIcon} onClick={buildSelected} disabled={busy} className="split__main" title="Ctrl B">
          {t('Compiler', 'Build')}
        </Button>
        <Button ref={more} tone="primary" size="sm" icon={ArrowDown01Icon} title={t('Plus', 'More')} onClick={() => setOpen(!open)} expanded={open} disabled={busy} className="split__more" />
      </div>
      <Button
        tone="secondary"
        size="sm"
        icon={PlayIcon}
        onClick={runSelected}
        disabled={busy || !runnable}
        title={runnable ? t(`Exécuter ${startup} · Ctrl F5`, `Run ${startup} · Ctrl F5`) : t('Aucun exécutable de démarrage', 'No startup executable')}
        className="build__run"
      />
      <Popover anchor={more} open={open} onClose={close} width={270} align="end">
        <Menu
          items={[
            { value: 'run', label: t('Exécuter', 'Run'), icon: PlayIcon, tag: <Kbd>Ctrl F5</Kbd> },
            { value: 'all', label: t('Tout compiler', 'Build all'), icon: Layers01Icon, tag: <Kbd>{t('Ctrl Maj B', 'Ctrl Shift B')}</Kbd> },
            { value: 'generate', label: t('Générer la solution', 'Generate the solution'), icon: RefreshIcon }
          ]}
          onSelect={value => {
            setOpen(false);
            if (value === 'run') runSelected();
            else if (value === 'all') buildAll();
            else generate();
          }}
        />
      </Popover>
      <Matrix />
    </div>
  );
}

function Matrix() {
  const matrix = useStore(s => s.matrix);
  const running = matrix?.some(p => p.status === 'running' || p.status === 'pending');
  useEffect(() => {
    if (!matrix || running) return;
    const close = (event: PointerEvent) => {
      if (!(event.target as HTMLElement).closest('.matrix')) setState({ matrix: null });
    };
    window.addEventListener('pointerdown', close);
    return () => window.removeEventListener('pointerdown', close);
  }, [matrix, running]);
  return (
    <AnimatePresence>
      {matrix ? (
        <motion.div
          className="matrix"
          initial={{ opacity: 0, y: -6, scale: 0.96, filter: 'blur(6px)' }}
          animate={{ opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, y: -4, scale: 0.98, filter: 'blur(4px)' }}
          transition={{ type: 'spring', bounce: 0, duration: 0.32 }}
        >
          {matrix.map(p => (
            <div key={`${p.configuration}|${p.platform}`} className="matrix__row">
              <StatusMark
                status={p.status === 'failed' ? 'failed' : p.status}
                label={
                  <>
                    <span className="matrix__config">{p.configuration}</span>
                    <span className="matrix__platform">{p.platform}</span>
                  </>
                }
                size={16}
                fontSize={12.5}
                strike={false}
                color="var(--text)"
                doneColor="var(--success)"
                errorColor="var(--danger)"
                spoken={statusWords()}
              />
            </div>
          ))}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

// Une version plus récente, déjà téléchargée : un clic redémarre CStarter sur elle.
function UpdateChip() {
  const update = useStore(s => s.update);
  return (
    <AnimatePresence>
      {update ? (
        <motion.button
          className="titlebar__update no-drag"
          onClick={installUpdate}
          initial={{ opacity: 0, scale: 0.9, filter: 'blur(6px)' }}
          animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 0.95, filter: 'blur(4px)' }}
          transition={{ type: 'spring', bounce: 0.3, duration: 0.5 }}
        >
          <Icon icon={SystemUpdate01Icon} size={14} stroke={1.8} />
          <span>{t('Mettre à jour', 'Update')}</span>
          <span className="titlebar__update-version">{update}</span>
        </motion.button>
      ) : null}
    </AnimatePresence>
  );
}

function RunChip() {
  const run = useStore(s => s.run);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!run) return;
    setVisible(true);
    if (run.status === 'running') return;
    const timer = setTimeout(() => setVisible(false), run.status === 'done' ? 6000 : 12000);
    return () => clearTimeout(timer);
  }, [run]);
  return (
    <AnimatePresence>
      {run && visible ? (
        <motion.div
          key={run.id}
          className="titlebar__run no-drag"
          initial={{ opacity: 0, x: 12, filter: 'blur(6px)' }}
          animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, x: 8, filter: 'blur(6px)' }}
          transition={{ type: 'spring', bounce: 0, duration: 0.35 }}
          onClick={() => setState(s => ({ panel: { ...s.panel, open: true, tab: 'output' } }))}
        >
          <CallChip
            icon="terminal"
            name={run.name}
            argument={run.argument}
            status={run.status === 'error' ? 'error' : run.status}
            expectedMs={EXPECTED[run.kind] ?? 4000}
            size={28}
            radius={9}
            surfaceColor="rgba(255,255,255,0.05)"
            progressColor="#8e8cff"
            progressOpacity={0.16}
            doneColor="#3ddc97"
            errorColor="#ff6b6b"
          />
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function WindowControls({ maximized }: { maximized: boolean }) {
  return (
    <div className="window-controls no-drag">
      <button className="window-controls__button" aria-label={t('Réduire', 'Minimize')} onClick={() => call('window_minimize')}>
        {''}
      </button>
      <button
        className="window-controls__button"
        aria-label={maximized ? t('Restaurer', 'Restore') : t('Agrandir', 'Maximize')}
        onClick={() => call('window_toggle_maximize')}
      >
        {maximized ? '' : ''}
      </button>
      <button className="window-controls__button window-controls__button--close" aria-label={t('Fermer', 'Close')} onClick={requestClose}>
        {''}
      </button>
    </div>
  );
}
